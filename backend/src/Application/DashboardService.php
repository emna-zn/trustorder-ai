<?php

declare(strict_types=1);

namespace App\Application;

use App\Domain\Model\CustomerHistory;
use App\Domain\Port\TrustOrderStore;
use App\Infrastructure\Scoring\FastApiClient;

final class DashboardService
{
    public function __construct(private readonly TrustOrderStore $store, private readonly FastApiClient $engine)
    {
    }

    /** @return array<string, mixed> */
    public function build(Actor $actor): array
    {
        $this->pushStoredSettings();
        $shopId = $actor->scope();
        $today = (new \DateTimeImmutable('today'))->format('Y-m-d');
        $yesterday = (new \DateTimeImmutable('yesterday'))->format('Y-m-d');
        $week = (new \DateTimeImmutable('today'))->modify('-7 days')->format('Y-m-d');
        $ordersToday = $this->store->countOrdersOn($today, $shopId);
        $ordersYesterday = $this->store->countOrdersOn($yesterday, $shopId);
        $hashes = $this->store->distinctHashes($shopId);
        $now = $this->store->histories($hashes, $today);
        $old = $this->store->histories($hashes, $week);
        $current = $this->engine->analyzeMany($this->items($hashes, $now));
        $previous = $this->engine->analyzeMany($this->items($hashes, $old));

        $scores = [];
        $oldScores = [];
        $risks = ['LOW' => 0, 'MEDIUM' => 0, 'HIGH' => 0];
        $cold = 0;
        $retentions = [];
        $model = null;
        foreach ($hashes as $hash) {
            $analysis = $current[$hash] ?? null;
            if ($analysis === null) {
                continue;
            }
            $scores[] = (float) $analysis['score'];
            $level = (string) $analysis['risk_level'];
            if (isset($risks[$level])) {
                ++$risks[$level];
            }
            if (!empty($analysis['cold_start'])) {
                ++$cold;
            } elseif ($analysis['retention_probability'] !== null) {
                $retentions[] = (float) $analysis['retention_probability'];
                $model = $analysis['model_version'] ?? $model;
            }
            if (isset($previous[$hash]['score'])) {
                $oldScores[] = (float) $previous[$hash]['score'];
            }
        }

        $pending = $this->store->pendingAmounts($shopId);
        $prioItems = [];
        foreach ($pending as $row) {
            $prioItems[] = [
                'customer_ref' => (string) $row['id'],
                'history' => $now[$row['phone_hash']] ?? CustomerHistory::empty(),
                'order' => ['order_id' => (string) $row['id'], 'amount' => max(0.001, $row['amount'])],
            ];
        }
        $priorities = $prioItems === [] ? [] : $this->engine->prioritizeMany($prioItems);
        $high = 0;
        foreach ($priorities as $priority) {
            if (($priority['priority'] ?? '') === 'HIGH') {
                ++$high;
            }
        }

        $preview = [];
        foreach ($this->store->pendingPreview($shopId, 80) as $row) {
            $analysis = $current[$row['phone_hash']] ?? $this->engine->analyze($now[$row['phone_hash']] ?? CustomerHistory::empty(), $row['phone_hash']);
            $priority = $priorities[(string) $row['id']] ?? $this->engine->prioritize(
                $now[$row['phone_hash']] ?? CustomerHistory::empty(),
                ['order_id' => (string) $row['id'], 'amount' => max(0.001, (float) $row['amount'])],
                (string) $row['id']
            );
            $preview[] = [
                'order_id' => $row['id'],
                'customer' => $row['full_name'],
                'phone_mask' => $row['phone_mask'],
                'shop' => $row['shop'],
                'label' => $row['label'],
                'amount' => $row['amount'],
                'score' => $analysis['score'],
                'risk_level' => $analysis['risk_level'],
                'priority_score' => $priority['priority_score'],
                'priority' => $priority['priority'],
                'explanation' => $priority['explanation'],
                'cold_start' => $analysis['cold_start'],
                'prediction_source' => $analysis['prediction_source'],
                'engine' => EngineNote::forAnalysis($analysis),
            ];
        }
        usort($preview, static fn (array $a, array $b) => $b['priority_score'] <=> $a['priority_score']);
        $customers = count($hashes);
        $mean = $this->avg($scores);
        $meanOld = $this->avg($oldScores);

        return [
            'date' => $today,
            'scope' => $shopId === null ? 'global' : 'boutique',
            'orders_today' => $ordersToday,
            'orders_yesterday' => $ordersYesterday,
            'orders_delta_pct' => $ordersYesterday === 0 ? null : round(($ordersToday - $ordersYesterday) / $ordersYesterday * 100, 1),
            'mean_score' => $mean,
            'mean_score_delta_7d' => ($mean === null || $meanOld === null) ? null : round($mean - $meanOld, 1),
            'high_priority_pending' => $high,
            'mean_retention' => $retentions === [] ? null : round(array_sum($retentions) / count($retentions) * 100, 1),
            'retention_sample' => count($retentions),
            'model_version' => $model,
            'customers' => $customers,
            'cold_start_pct' => $customers === 0 ? 0 : round(100 * $cold / $customers, 1),
            'cold_start_count' => $cold,
            'risk' => $risks,
            'totals' => $this->store->orderTotals($shopId),
            'priority_preview' => array_slice($preview, 0, 6),
            'recent_orders' => $this->store->recentOrders($shopId, 8),
            'engine' => [
                'calculated_by' => 'moteur.analyser_client + moteur.prioriser_commande via FastAPI',
                'score_is_live' => true,
                'retention_excludes_cold_start' => true,
            ],
        ];
    }

    /** @return array<string, mixed> */
    public function priorityList(Actor $actor, int $limit): array
    {
        $this->pushStoredSettings();
        $shopId = $actor->scope();
        $rows = $this->store->pendingPreview($shopId, max(1, min(80, $limit)));
        $hashes = array_column($rows, 'phone_hash');
        $histories = $this->store->histories($hashes, (new \DateTimeImmutable('today'))->format('Y-m-d'));
        $analyses = $this->engine->analyzeMany($this->items($hashes, $histories));
        $batch = [];
        foreach ($rows as $row) {
            $batch[] = [
                'customer_ref' => (string) $row['id'],
                'history' => $histories[$row['phone_hash']] ?? CustomerHistory::empty(),
                'order' => ['order_id' => (string) $row['id'], 'amount' => max(0.001, (float) $row['amount'])],
            ];
        }
        $priorities = $batch === [] ? [] : $this->engine->prioritizeMany($batch);
        $items = [];
        foreach ($rows as $row) {
            $analysis = $analyses[$row['phone_hash']] ?? [];
            $priority = $priorities[(string) $row['id']] ?? [];
            $items[] = [
                'customer' => $row['full_name'],
                'phone_mask' => $row['phone_mask'],
                'label' => $row['label'],
                'order_date' => $row['order_date'],
                'shop' => $row['shop'],
                'amount' => $row['amount'],
                'score' => $analysis['score'] ?? null,
                'priority' => $priority['priority'] ?? null,
                'priority_score' => $priority['priority_score'] ?? null,
                'explanation' => $priority['explanation'] ?? '',
                'cold_start' => $analysis['cold_start'] ?? true,
            ];
        }
        usort($items, static fn (array $a, array $b) => ($b['priority_score'] ?? 0) <=> ($a['priority_score'] ?? 0));

        return [
            'items' => $items,
            'engine' => ['calculated_by' => 'FastAPI /v1/prioritize/batch → service/moteur.py'],
        ];
    }

    /** @return array<string, mixed> */
    public function adminStats(): array
    {
        $globalActor = new Actor(0, 'stats@trustorder.tn', 'Stats', 'ADMIN', null, null, null, null);
        $global = $this->build($globalActor);
        $per = [];
        foreach ($this->store->listShops() as $shop) {
            $local = new Actor(0, 'stats@trustorder.tn', 'Stats', 'SHOP', $shop['id'], $shop['name'], $shop['city'], $shop['governorate']);
            $dash = $this->build($local);
            $per[] = [
                'id' => $shop['id'],
                'name' => $shop['name'],
                'governorate' => $shop['governorate'],
                'city' => $shop['city'],
                'active' => $shop['active'],
                'orders' => $dash['totals']['orders'],
                'customers' => $dash['customers'],
                'mean_score' => $dash['mean_score'],
                'high_priority_pending' => $dash['high_priority_pending'],
                'cold_start_pct' => $dash['cold_start_pct'],
                'risk' => $dash['risk'],
            ];
        }

        return ['global' => $global, 'boutiques' => $per];
    }

    /**
     * @param list<string> $hashes
     * @param array<string, array<string, int>> $histories
     * @return list<array{customer_ref: string, history: array<string, int>}>
     */
    private function items(array $hashes, array $histories): array
    {
        $items = [];
        foreach (array_unique($hashes) as $hash) {
            $items[] = [
                'customer_ref' => $hash,
                'history' => $histories[$hash] ?? CustomerHistory::empty(),
            ];
        }

        return $items;
    }

    /** @param list<float> $values */
    private function avg(array $values): ?float
    {
        if ($values === []) {
            return null;
        }

        return round(array_sum($values) / count($values), 1);
    }

    private function pushStoredSettings(): void
    {
        $stored = $this->store->settings();
        if ($stored === []) {
            return;
        }
        $payload = [];
        foreach ($stored as $key => $value) {
            $payload[$key] = str_contains($value, '.') ? (float) $value : (int) $value;
        }
        $this->engine->putSettings($payload);
    }
}
