<?php

declare(strict_types=1);

namespace App\Infrastructure\Persistence;

use App\Domain\Exception\DomainException;
use App\Domain\Model\CustomerHistory;
use App\Domain\Port\TrustOrderStore;
use App\Infrastructure\Persistence\Entity\ComplaintEntity;
use App\Infrastructure\Persistence\Entity\ContestationEntity;
use App\Infrastructure\Persistence\Entity\CustomerEntity;
use App\Infrastructure\Persistence\Entity\OrderEntity;
use App\Infrastructure\Persistence\Entity\SettingEntity;
use App\Infrastructure\Persistence\Entity\ShopEntity;
use App\Infrastructure\Persistence\Entity\UserEntity;
use Doctrine\DBAL\ArrayParameterType;
use Doctrine\DBAL\Connection;
use Doctrine\DBAL\ParameterType;
use Doctrine\ORM\EntityManagerInterface;

final class DoctrineTrustOrderStore implements TrustOrderStore
{
    public function __construct(private readonly EntityManagerInterface $em)
    {
    }

    public function findUserByEmail(string $email): ?array
    {
        $row = $this->db()->fetchAssociative(
            'SELECT u.id, u.email, u.password, u.full_name, u.role, u.active, u.boutique_id,
                    b.name AS shop_name, b.city AS shop_city, b.governorate AS shop_governorate, b.active AS shop_active
             FROM app_user u
             LEFT JOIN boutique b ON b.id = u.boutique_id
             WHERE u.email = :email',
            ['email' => mb_strtolower(trim($email))]
        );

        return $row === false ? null : $this->userRow($row);
    }

    public function userIdByEmail(string $email): ?int
    {
        $id = $this->db()->fetchOne('SELECT id FROM app_user WHERE email = :email', ['email' => mb_strtolower(trim($email))]);

        return $id === false ? null : (int) $id;
    }

    public function countOrdersOn(string $day, ?int $shopId): int
    {
        $params = ['day' => $day];
        $shop = $this->shopSql($shopId, 'boutique_id', $params);

        return (int) $this->db()->fetchOne('SELECT COUNT(*) FROM customer_order WHERE order_date = :day'.$shop, $params);
    }

    public function orderTotals(?int $shopId): array
    {
        $params = [];
        $shop = $this->shopSql($shopId, 'boutique_id', $params);
        $where = $shop === '' ? '' : 'WHERE '.ltrim($shop, ' AND ');
        $row = $this->db()->fetchAssociative(
            "SELECT COUNT(*) AS orders,
                    SUM(status = 'DELIVERED') AS delivered,
                    SUM(status = 'REFUSED') AS refused,
                    SUM(status = 'NOT_COLLECTED') AS not_collected
             FROM customer_order $where",
            $params
        ) ?: [];

        return [
            'orders' => (int) ($row['orders'] ?? 0),
            'delivered' => (int) ($row['delivered'] ?? 0),
            'refused' => (int) ($row['refused'] ?? 0),
            'not_collected' => (int) ($row['not_collected'] ?? 0),
        ];
    }

    public function distinctHashes(?int $shopId): array
    {
        $params = [];
        $shop = $this->shopSql($shopId, 'boutique_id', $params);
        $where = $shop === '' ? '' : 'WHERE '.ltrim($shop, ' AND ');
        $rows = $this->db()->fetchFirstColumn('SELECT DISTINCT phone_hash FROM customer_order '.$where, $params);

        return array_map('strval', $rows);
    }

    public function histories(array $hashes, string $asOf): array
    {
        $found = [];
        $recentFrom = (new \DateTimeImmutable($asOf))->modify('-90 days')->format('Y-m-d');
        foreach (array_chunk(array_values(array_unique($hashes)), 400) as $batch) {
            if ($batch === []) {
                continue;
            }
            $params = ['asOf' => $asOf, 'recent' => $recentFrom, 'hashes' => $batch];
            $types = ['hashes' => ArrayParameterType::STRING];
            $rows = $this->db()->fetchAllAssociative(
                "SELECT phone_hash AS h,
                        SUM(status = 'DELIVERED') AS delivered_orders,
                        SUM(status = 'REFUSED') AS refused_orders,
                        SUM(status = 'NOT_COLLECTED') AS not_collected_orders,
                        SUM(status IN ('REFUSED','NOT_COLLECTED') AND order_date >= :recent) AS recent_failed_90d,
                        COUNT(DISTINCT boutique_id) AS distinct_shops
                 FROM customer_order
                 WHERE phone_hash IN (:hashes) AND order_date <= :asOf
                 GROUP BY phone_hash",
                $params,
                $types
            );
            $reports = $this->db()->fetchAllAssociative(
                "SELECT phone_hash AS h, COUNT(*) AS n
                 FROM complaint
                 WHERE status = 'CONFIRME' AND phone_hash IN (:hashes) AND DATE(created_at) <= :asOf
                 GROUP BY phone_hash",
                ['hashes' => $batch, 'asOf' => $asOf],
                ['hashes' => ArrayParameterType::STRING]
            );
            $byHash = [];
            foreach ($reports as $report) {
                $byHash[$report['h']] = (int) $report['n'];
            }
            foreach ($rows as $row) {
                $history = CustomerHistory::fromRow($row);
                $history['reports_count'] = $byHash[$row['h']] ?? 0;
                $found[$row['h']] = $history;
            }
        }

        return $found;
    }

    public function pendingPreview(?int $shopId, int $limit): array
    {
        $params = ['limit' => $limit];
        $shop = $this->shopSql($shopId, 'o.boutique_id', $params);
        $rows = $this->db()->fetchAllAssociative(
            "SELECT o.id, o.amount, o.phone_hash, o.label, o.order_date, o.status,
                    c.full_name, c.phone_mask, b.name AS shop
             FROM customer_order o
             JOIN customer c ON c.id = o.customer_id
             JOIN boutique b ON b.id = o.boutique_id
             WHERE o.status = 'PENDING' $shop
             ORDER BY o.order_date DESC, o.id DESC
             LIMIT :limit",
            $params,
            ['limit' => ParameterType::INTEGER]
        );

        return array_map(fn (array $row) => $this->orderLite($row), $rows);
    }

    public function pendingAmounts(?int $shopId): array
    {
        $params = [];
        $shop = $this->shopSql($shopId, 'boutique_id', $params);
        $rows = $this->db()->fetchAllAssociative(
            "SELECT id, amount, phone_hash FROM customer_order WHERE status = 'PENDING' $shop",
            $params
        );

        return array_map(static fn (array $row) => [
            'id' => (int) $row['id'],
            'amount' => (float) $row['amount'],
            'phone_hash' => (string) $row['phone_hash'],
        ], $rows);
    }

    public function recentOrders(?int $shopId, int $limit): array
    {
        $params = ['limit' => $limit];
        $shop = $this->shopSql($shopId, 'o.boutique_id', $params);
        $where = $shop === '' ? '' : 'WHERE '.ltrim($shop, ' AND ');
        $rows = $this->db()->fetchAllAssociative(
            "SELECT o.id, c.full_name, c.phone_mask, o.label, o.status, o.amount, o.order_date, b.name AS shop
             FROM customer_order o
             JOIN customer c ON c.id = o.customer_id
             JOIN boutique b ON b.id = o.boutique_id
             $where
             ORDER BY o.order_date DESC, o.id DESC
             LIMIT :limit",
            $params,
            ['limit' => ParameterType::INTEGER]
        );

        return array_map(fn (array $row) => [
            'id' => (int) $row['id'],
            'full_name' => $row['full_name'],
            'phone_mask' => $row['phone_mask'],
            'label' => $row['label'],
            'status' => $row['status'],
            'amount' => (float) $row['amount'],
            'order_date' => $this->day($row['order_date']),
            'shop' => $row['shop'],
        ], $rows);
    }

    public function searchOrders(?int $shopId, string $status, string $query, int $page, int $pageSize): array
    {
        $params = [];
        $clauses = [];
        if ($shopId !== null) {
            $clauses[] = 'o.boutique_id = :shopId';
            $params['shopId'] = $shopId;
        }
        if (in_array($status, ['PENDING', 'DELIVERED', 'REFUSED', 'NOT_COLLECTED'], true)) {
            $clauses[] = 'o.status = :status';
            $params['status'] = $status;
        }
        if (trim($query) !== '') {
            $clauses[] = '(c.full_name LIKE :q OR o.label LIKE :q OR c.phone_mask LIKE :q OR c.phone_normalized LIKE :q)';
            $params['q'] = '%'.trim($query).'%';
        }
        $where = $clauses === [] ? '' : 'WHERE '.implode(' AND ', $clauses);
        $total = (int) $this->db()->fetchOne(
            "SELECT COUNT(*) FROM customer_order o JOIN customer c ON c.id = o.customer_id $where",
            $params
        );
        $params['limit'] = $pageSize;
        $params['offset'] = ($page - 1) * $pageSize;
        $rows = $this->db()->fetchAllAssociative(
            "SELECT o.id, o.label, o.amount, o.status, o.order_date, o.boutique_id, b.name AS shop,
                    c.full_name, c.phone_mask, c.phone_normalized, c.city
             FROM customer_order o
             JOIN customer c ON c.id = o.customer_id
             JOIN boutique b ON b.id = o.boutique_id
             $where
             ORDER BY o.order_date DESC, o.id DESC
             LIMIT :limit OFFSET :offset",
            $params,
            ['limit' => ParameterType::INTEGER, 'offset' => ParameterType::INTEGER]
        );
        $items = array_map(fn (array $row) => [
            'id' => (int) $row['id'],
            'label' => $row['label'],
            'amount' => (float) $row['amount'],
            'status' => $row['status'],
            'order_date' => $this->day($row['order_date']),
            'boutique_id' => (int) $row['boutique_id'],
            'shop' => $row['shop'],
            'full_name' => $row['full_name'],
            'phone_mask' => $row['phone_mask'],
            'phone_normalized' => $row['phone_normalized'],
            'city' => $row['city'],
        ], $rows);

        return ['items' => $items, 'total' => $total];
    }

    public function customerCount(?int $shopId): int
    {
        return count($this->distinctHashes($shopId));
    }

    public function findCustomerByHash(string $hash): ?array
    {
        $row = $this->db()->fetchAssociative(
            'SELECT id, full_name, city, governorate, phone_mask, phone_normalized FROM customer WHERE phone_hash = :hash',
            ['hash' => $hash]
        );

        return $row === false ? null : $row;
    }

    public function ordersForPhone(string $hash, ?int $shopId, int $limit): array
    {
        $params = ['hash' => $hash, 'limit' => $limit];
        $shop = $this->shopSql($shopId, 'o.boutique_id', $params);
        $rows = $this->db()->fetchAllAssociative(
            "SELECT o.id, o.label, o.amount, o.status, o.order_date, b.name AS shop
             FROM customer_order o
             JOIN boutique b ON b.id = o.boutique_id
             WHERE o.phone_hash = :hash $shop
             ORDER BY o.order_date DESC
             LIMIT :limit",
            $params,
            ['limit' => ParameterType::INTEGER]
        );

        return array_map(fn (array $row) => [
            'id' => (int) $row['id'],
            'label' => $row['label'],
            'amount' => $row['amount'] === null ? null : (float) $row['amount'],
            'status' => $row['status'],
            'order_date' => $this->day($row['order_date']),
            'shop' => $shopId === null ? $row['shop'] : ($row['shop'] ?? ''),
        ], $rows);
    }

    public function upsertCustomer(string $name, string $phone, string $hash, string $mask, string $governorate, string $city): int
    {
        $existing = $this->em->getRepository(CustomerEntity::class)->findOneBy(['phoneHash' => $hash]);
        if ($existing instanceof CustomerEntity) {
            return (int) $existing->id;
        }
        $customer = new CustomerEntity();
        $customer->fullName = $name;
        $customer->phoneNormalized = $phone;
        $customer->phoneHash = $hash;
        $customer->phoneMask = $mask;
        $customer->governorate = $governorate;
        $customer->city = $city;
        $this->em->persist($customer);
        $this->em->flush();

        return (int) $customer->id;
    }

    public function insertOrder(int $shopId, int $customerId, string $hash, string $label, ?float $amount, string $status, string $day, string $fingerprint): int
    {
        if ($this->db()->fetchOne('SELECT 1 FROM customer_order WHERE fingerprint = :fp', ['fp' => $fingerprint])) {
            throw new DomainException('Cette commande semble déjà enregistrée (même numéro, date, montant et libellé).', 409);
        }
        $order = new OrderEntity();
        $order->boutique = $this->shopRef($shopId);
        $customer = $this->em->find(CustomerEntity::class, $customerId);
        if (!$customer instanceof CustomerEntity) {
            throw new DomainException('Client introuvable.', 404);
        }
        $order->customer = $customer;
        $order->phoneHash = $hash;
        $order->label = $label;
        $order->amount = $amount === null ? null : number_format($amount, 3, '.', '');
        $order->status = $status;
        $order->orderDate = new \DateTimeImmutable($day);
        $order->fingerprint = $fingerprint;
        $this->em->persist($order);
        $this->em->flush();

        return (int) $order->id;
    }

    public function findOrder(int $id): ?array
    {
        $row = $this->db()->fetchAssociative(
            'SELECT id, boutique_id, status, phone_hash, amount FROM customer_order WHERE id = :id',
            ['id' => $id]
        );

        return $row === false ? null : [
            'id' => (int) $row['id'],
            'boutique_id' => (int) $row['boutique_id'],
            'status' => $row['status'],
            'phone_hash' => $row['phone_hash'],
            'amount' => (float) $row['amount'],
        ];
    }

    public function confirmOrder(int $id, string $status): void
    {
        $order = $this->em->find(OrderEntity::class, $id);
        if (!$order instanceof OrderEntity) {
            throw new DomainException('Commande introuvable.', 404);
        }
        if ($order->status !== 'PENDING') {
            throw new DomainException('Seule une commande en attente peut être confirmée.', 409);
        }
        $order->status = $status;
        $this->em->flush();
    }

    public function addComplaint(int $shopId, string $hash, string $mask, string $motif): int
    {
        $row = new ComplaintEntity();
        $row->boutique = $this->shopRef($shopId);
        $row->phoneHash = $hash;
        $row->phoneMask = $mask;
        $row->motif = $motif;
        $this->em->persist($row);
        $this->em->flush();

        return (int) $row->id;
    }

    public function addContestation(int $shopId, string $hash, string $mask, string $motif): int
    {
        $row = new ContestationEntity();
        $row->boutique = $this->shopRef($shopId);
        $row->phoneHash = $hash;
        $row->phoneMask = $mask;
        $row->motif = $motif;
        $this->em->persist($row);
        $this->em->flush();

        return (int) $row->id;
    }

    public function listComplaints(?int $shopId): array
    {
        return $this->listCases('complaint', 'admin_note', $shopId);
    }

    public function listContestations(?int $shopId): array
    {
        return $this->listCases('contestation', 'decision_note', $shopId);
    }

    public function decideComplaint(int $id, string $status, string $note): void
    {
        $row = $this->em->find(ComplaintEntity::class, $id);
        if (!$row instanceof ComplaintEntity) {
            throw new DomainException('Signalement introuvable.', 404);
        }
        $row->status = $status;
        $row->adminNote = $note;
        $row->updatedAt = new \DateTimeImmutable();
        $this->em->flush();
    }

    public function decideContestation(int $id, string $status, string $note): void
    {
        $row = $this->em->find(ContestationEntity::class, $id);
        if (!$row instanceof ContestationEntity) {
            throw new DomainException('Contestation introuvable.', 404);
        }
        $row->status = $status;
        $row->decisionNote = $note;
        $row->updatedAt = new \DateTimeImmutable();
        $this->em->flush();
    }

    public function pendingComplaints(?int $shopId): array
    {
        $params = [];
        $shop = $this->shopSql($shopId, 'boutique_id', $params);
        $count = (int) $this->db()->fetchOne("SELECT COUNT(*) FROM complaint WHERE status = 'EN_ATTENTE' $shop", $params);
        $params['limit'] = 6;
        $items = $this->db()->fetchAllAssociative(
            "SELECT id, motif, phone_mask, created_at FROM complaint WHERE status = 'EN_ATTENTE' $shop ORDER BY id DESC LIMIT :limit",
            $params,
            ['limit' => ParameterType::INTEGER]
        );

        return ['count' => $count, 'items' => $items];
    }

    public function audit(string $email, string $action, string $details): void
    {
        $this->db()->insert('audit_log', [
            'actor_email' => $email,
            'action' => $action,
            'details' => mb_substr($details, 0, 500),
            'created_at' => (new \DateTimeImmutable())->format('Y-m-d H:i:s'),
        ]);
    }

    public function logAnalysis(?int $shopId, string $email, string $mask, string $hash, string $kind, array $analysis, ?string $priority, string $summary): void
    {
        $this->db()->insert('analysis_log', [
            'boutique_id' => $shopId,
            'actor_email' => $email,
            'phone_mask' => $mask,
            'phone_hash' => $hash,
            'kind' => $kind,
            'score' => $analysis['score'] ?? null,
            'risk_level' => $analysis['risk_level'] ?? null,
            'priority' => $priority,
            'cold_start' => !empty($analysis['cold_start']) ? 1 : 0,
            'retention_probability' => $analysis['retention_probability'] ?? null,
            'prediction_source' => $analysis['prediction_source'] ?? 'RULES',
            'summary' => mb_substr($summary, 0, 500),
            'created_at' => (new \DateTimeImmutable())->format('Y-m-d H:i:s'),
        ]);
    }

    public function listAnalyses(?int $shopId, int $page, int $pageSize): array
    {
        $params = [];
        $shop = $this->shopSql($shopId, 'boutique_id', $params);
        $where = $shop === '' ? '' : 'WHERE '.ltrim($shop, ' AND ');
        $total = (int) $this->db()->fetchOne("SELECT COUNT(*) FROM analysis_log $where", $params);
        $params['limit'] = $pageSize;
        $params['offset'] = ($page - 1) * $pageSize;
        $items = $this->db()->fetchAllAssociative(
            "SELECT id, created_at, actor_email, phone_mask, kind, score, risk_level, priority, cold_start, retention_probability, prediction_source, summary
             FROM analysis_log $where ORDER BY id DESC LIMIT :limit OFFSET :offset",
            $params,
            ['limit' => ParameterType::INTEGER, 'offset' => ParameterType::INTEGER]
        );
        foreach ($items as &$item) {
            $item['id'] = (int) $item['id'];
            $item['score'] = $item['score'] === null ? null : (int) $item['score'];
            $item['cold_start'] = (bool) $item['cold_start'];
            $item['retention_probability'] = $item['retention_probability'] === null ? null : (float) $item['retention_probability'];
        }

        return ['items' => $items, 'total' => $total];
    }

    public function settings(): array
    {
        return $this->db()->fetchAllKeyValue('SELECT setting_key, value FROM score_setting');
    }

    public function saveSettings(array $values): void
    {
        foreach ($values as $key => $value) {
            $row = $this->em->find(SettingEntity::class, $key);
            if (!$row instanceof SettingEntity) {
                $row = new SettingEntity();
                $row->settingKey = $key;
                $this->em->persist($row);
            }
            $row->value = (string) $value;
        }
        $this->em->flush();
    }

    public function clearSettings(): void
    {
        $this->db()->executeStatement('DELETE FROM score_setting');
    }

    public function listShops(): array
    {
        $rows = $this->db()->fetchAllAssociative(
            'SELECT b.id, b.name, b.governorate, b.city, b.address, b.active,
                    (SELECT COUNT(*) FROM customer_order o WHERE o.boutique_id = b.id) AS orders,
                    (SELECT COUNT(*) FROM app_user u WHERE u.boutique_id = b.id) AS users
             FROM boutique b ORDER BY b.id'
        );

        return array_map(static fn (array $row) => [
            'id' => (int) $row['id'],
            'name' => $row['name'],
            'governorate' => $row['governorate'],
            'city' => $row['city'],
            'address' => $row['address'],
            'active' => (bool) $row['active'],
            'orders' => (int) $row['orders'],
            'users' => (int) $row['users'],
        ], $rows);
    }

    public function createShop(string $name, string $governorate, string $city, string $address, bool $active): int
    {
        $shop = new ShopEntity();
        $shop->name = $name;
        $shop->governorate = $governorate;
        $shop->city = $city;
        $shop->address = $address;
        $shop->active = $active;
        $this->em->persist($shop);
        $this->em->flush();

        return (int) $shop->id;
    }

    public function setShopActive(int $id, bool $active): void
    {
        $shop = $this->em->find(ShopEntity::class, $id);
        if (!$shop instanceof ShopEntity) {
            throw new DomainException('Boutique introuvable.', 404);
        }
        $shop->active = $active;
        $this->em->flush();
    }

    public function listUsers(): array
    {
        $rows = $this->db()->fetchAllAssociative(
            'SELECT u.id, u.email, u.full_name, u.role, u.active, u.boutique_id, b.name AS shop
             FROM app_user u LEFT JOIN boutique b ON b.id = u.boutique_id ORDER BY u.id'
        );

        return array_map(static fn (array $row) => [
            'id' => (int) $row['id'],
            'email' => $row['email'],
            'full_name' => $row['full_name'],
            'role' => $row['role'],
            'active' => (bool) $row['active'],
            'boutique_id' => $row['boutique_id'] === null ? null : (int) $row['boutique_id'],
            'shop' => $row['shop'],
        ], $rows);
    }

    public function emailExists(string $email): bool
    {
        return (bool) $this->db()->fetchOne('SELECT 1 FROM app_user WHERE email = :email', ['email' => mb_strtolower(trim($email))]);
    }

    public function createUser(string $email, string $passwordHash, string $fullName, string $role, ?int $shopId): int
    {
        $user = new UserEntity();
        $user->email = mb_strtolower(trim($email));
        $user->password = $passwordHash;
        $user->fullName = $fullName;
        $user->role = $role;
        $user->active = true;
        if ($shopId !== null) {
            $user->boutique = $this->shopRef($shopId);
        }
        $this->em->persist($user);
        $this->em->flush();

        return (int) $user->id;
    }

    public function setUserActive(int $id, bool $active): bool
    {
        $user = $this->em->find(UserEntity::class, $id);
        if (!$user instanceof UserEntity) {
            return false;
        }
        $user->active = $active;
        $this->em->flush();

        return true;
    }

    private function db(): Connection
    {
        return $this->em->getConnection();
    }

    /** @param array<string, mixed> $params */
    private function shopSql(?int $shopId, string $column, array &$params): string
    {
        if ($shopId === null) {
            return '';
        }
        $params['shopId'] = $shopId;

        return " AND $column = :shopId";
    }

    private function shopRef(int $shopId): ShopEntity
    {
        $shop = $this->em->find(ShopEntity::class, $shopId);
        if (!$shop instanceof ShopEntity) {
            throw new DomainException('Boutique introuvable.', 404);
        }

        return $shop;
    }

    /** @param array<string, mixed> $row */
    private function userRow(array $row): array
    {
        return [
            'id' => (int) $row['id'],
            'email' => $row['email'],
            'password' => $row['password'],
            'full_name' => $row['full_name'],
            'role' => $row['role'],
            'active' => (bool) $row['active'],
            'boutique_id' => $row['boutique_id'] === null ? null : (int) $row['boutique_id'],
            'shop_name' => $row['shop_name'],
            'shop_city' => $row['shop_city'],
            'shop_governorate' => $row['shop_governorate'],
            'shop_active' => $row['shop_active'] === null ? null : (bool) $row['shop_active'],
        ];
    }

    /** @param array<string, mixed> $row */
    private function orderLite(array $row): array
    {
        return [
            'id' => (int) $row['id'],
            'amount' => (float) $row['amount'],
            'phone_hash' => $row['phone_hash'],
            'label' => $row['label'],
            'order_date' => $this->day($row['order_date']),
            'status' => $row['status'],
            'full_name' => $row['full_name'],
            'phone_mask' => $row['phone_mask'],
            'shop' => $row['shop'],
        ];
    }

    /** @return list<array<string, mixed>> */
    private function listCases(string $table, string $noteColumn, ?int $shopId): array
    {
        $params = [];
        $shop = $this->shopSql($shopId, 'c.boutique_id', $params);
        $rows = $this->db()->fetchAllAssociative(
            "SELECT c.id, b.name AS shop, c.phone_mask, c.motif, c.status, c.$noteColumn AS note, c.created_at
             FROM $table c JOIN boutique b ON b.id = c.boutique_id
             WHERE 1 = 1 $shop ORDER BY c.id DESC",
            $params
        );
        $noteKey = $table === 'complaint' ? 'admin_note' : 'decision_note';

        return array_map(static fn (array $row) => [
            'id' => (int) $row['id'],
            'shop' => $row['shop'],
            'phone_mask' => $row['phone_mask'],
            'motif' => $row['motif'],
            'status' => $row['status'],
            $noteKey => $row['note'],
            'created_at' => $row['created_at'],
        ], $rows);
    }

    private function day(mixed $value): string
    {
        if ($value instanceof \DateTimeInterface) {
            return $value->format('Y-m-d');
        }

        return substr((string) $value, 0, 10);
    }
}
