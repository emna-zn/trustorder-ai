<?php

declare(strict_types=1);

namespace App\Infrastructure\Security;

use Symfony\Component\Security\Core\User\PasswordAuthenticatedUserInterface;
use Symfony\Component\Security\Core\User\UserInterface;

final class SecurityUser implements UserInterface, PasswordAuthenticatedUserInterface
{
    public function __construct(
        private readonly string $email,
        private readonly string $password,
        private readonly string $role,
        private readonly bool $active,
    ) {
    }

    public function getRoles(): array
    {
        if (!$this->active) {
            return [];
        }

        return $this->role === 'ADMIN' ? ['ROLE_ADMIN', 'ROLE_USER'] : ['ROLE_SHOP', 'ROLE_USER'];
    }

    public function getPassword(): string
    {
        return $this->password;
    }

    public function eraseCredentials(): void
    {
    }

    public function getUserIdentifier(): string
    {
        return $this->email;
    }
}
