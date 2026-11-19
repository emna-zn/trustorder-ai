<?php

declare(strict_types=1);

namespace App\Infrastructure\Security;

use App\Domain\Port\PasswordHasher;
use Symfony\Component\PasswordHasher\Hasher\NativePasswordHasher as SymfonyNative;

final class NativePasswordHasher implements PasswordHasher
{
    private SymfonyNative $hasher;

    public function __construct()
    {
        $this->hasher = new SymfonyNative();
    }

    public function hash(string $plain): string
    {
        return $this->hasher->hash($plain);
    }

    public function verify(string $plain, string $passwordHash): bool
    {
        return $this->hasher->verify($passwordHash, $plain);
    }
}
