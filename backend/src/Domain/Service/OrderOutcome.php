<?php

declare(strict_types=1);

namespace App\Domain\Service;

use App\Domain\Exception\DomainException;

final class OrderOutcome
{
    public const PENDING = 'PENDING';
    public const DELIVERED = 'DELIVERED';
    public const REFUSED = 'REFUSED';
    public const NOT_COLLECTED = 'NOT_COLLECTED';

    public static function assertClosed(string $status): string
    {
        $status = strtoupper(trim($status));
        if (!in_array($status, [self::DELIVERED, self::REFUSED, self::NOT_COLLECTED], true)) {
            throw new DomainException('Issue attendue : DELIVERED, REFUSED ou NOT_COLLECTED.');
        }

        return $status;
    }
}
