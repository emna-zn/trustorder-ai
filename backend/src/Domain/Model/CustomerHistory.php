<?php

declare(strict_types=1);

namespace App\Domain\Model;

final class CustomerHistory
{
    /** @return array{delivered_orders: int, refused_orders: int, not_collected_orders: int, recent_failed_90d: int, distinct_shops: int, reports_count: int} */
    public static function empty(): array
    {
        return [
            'delivered_orders' => 0,
            'refused_orders' => 0,
            'not_collected_orders' => 0,
            'recent_failed_90d' => 0,
            'distinct_shops' => 0,
            'reports_count' => 0,
        ];
    }

    /** @param array<string, int|string> $row */
    public static function fromRow(array $row): array
    {
        $history = self::empty();
        foreach ($history as $key => $_) {
            $history[$key] = (int) ($row[$key] ?? 0);
        }

        return $history;
    }

    /** @param array<string, int> $history */
    public static function settledOrders(array $history): int
    {
        return $history['delivered_orders'] + $history['refused_orders'] + $history['not_collected_orders'];
    }
}
