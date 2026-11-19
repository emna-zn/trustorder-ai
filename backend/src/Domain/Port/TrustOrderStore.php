<?php

declare(strict_types=1);

namespace App\Domain\Port;

interface TrustOrderStore
{
    public function findUserByEmail(string $email): ?array;

    public function userIdByEmail(string $email): ?int;

    public function countOrdersOn(string $day, ?int $shopId): int;

    /** @return array{orders: int, delivered: int, refused: int, not_collected: int} */
    public function orderTotals(?int $shopId): array;

    /** @return list<string> */
    public function distinctHashes(?int $shopId): array;

    /** @param list<string> $hashes
     *  @return array<string, array<string, int>>
     */
    public function histories(array $hashes, string $asOf): array;

    /** @return list<array<string, mixed>> */
    public function pendingPreview(?int $shopId, int $limit): array;

    /** @return list<array{id: int, amount: float, phone_hash: string}> */
    public function pendingAmounts(?int $shopId): array;

    /** @return list<array<string, mixed>> */
    public function recentOrders(?int $shopId, int $limit): array;

    /** @return array{items: list<array<string, mixed>>, total: int} */
    public function searchOrders(?int $shopId, string $status, string $query, int $page, int $pageSize): array;

    public function customerCount(?int $shopId): int;

    public function findCustomerByHash(string $hash): ?array;

    /** @return list<array<string, mixed>> */
    public function ordersForPhone(string $hash, ?int $shopId, int $limit): array;

    public function upsertCustomer(string $name, string $phone, string $hash, string $mask, string $governorate, string $city): int;

    public function insertOrder(int $shopId, int $customerId, string $hash, string $label, ?float $amount, string $status, string $day, string $fingerprint): int;

    public function findOrder(int $id): ?array;

    public function confirmOrder(int $id, string $status): void;

    public function addComplaint(int $shopId, string $hash, string $mask, string $motif): int;

    public function addContestation(int $shopId, string $hash, string $mask, string $motif): int;

    /** @return list<array<string, mixed>> */
    public function listComplaints(?int $shopId): array;

    /** @return list<array<string, mixed>> */
    public function listContestations(?int $shopId): array;

    public function decideComplaint(int $id, string $status, string $note): void;

    public function decideContestation(int $id, string $status, string $note): void;

    /** @return array{count: int, items: list<array<string, mixed>>} */
    public function pendingComplaints(?int $shopId): array;

    public function audit(string $email, string $action, string $details): void;

    public function logAnalysis(?int $shopId, string $email, string $mask, string $hash, string $kind, array $analysis, ?string $priority, string $summary): void;

    /** @return array{items: list<array<string, mixed>>, total: int} */
    public function listAnalyses(?int $shopId, int $page, int $pageSize): array;

    /** @return array<string, string> */
    public function settings(): array;

    /** @param array<string, int|float> $values */
    public function saveSettings(array $values): void;

    public function clearSettings(): void;

    /** @return list<array<string, mixed>> */
    public function listShops(): array;

    public function createShop(string $name, string $governorate, string $city, string $address, bool $active): int;

    public function setShopActive(int $id, bool $active): void;

    /** @return list<array<string, mixed>> */
    public function listUsers(): array;

    public function emailExists(string $email): bool;

    public function createUser(string $email, string $passwordHash, string $fullName, string $role, ?int $shopId): int;

    public function setUserActive(int $id, bool $active): bool;
}
