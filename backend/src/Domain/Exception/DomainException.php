<?php

declare(strict_types=1);

namespace App\Domain\Exception;

final class DomainException extends \RuntimeException
{
    public function __construct(string $message, int $status = 422)
    {
        parent::__construct($message, $status);
    }

    public function status(): int
    {
        return $this->getCode() >= 400 ? $this->getCode() : 422;
    }
}
