<?php

declare(strict_types=1);

namespace App\Domain\Service;

/** HMAC-SHA256, identique à telephone.hacher (clé = secret, message = numéro normalisé). */
final class PhoneHasher
{
    public function __construct(private readonly string $secret)
    {
    }

    public function hash(string $normalized): string
    {
        return hash_hmac('sha256', $normalized, $this->secret);
    }
}
