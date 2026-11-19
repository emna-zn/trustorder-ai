<?php

declare(strict_types=1);

namespace App\Application;

use App\Domain\Exception\DomainException;
use App\Domain\Port\PasswordHasher;
use App\Domain\Port\TrustOrderStore;

final class AuthService
{
    public function __construct(
        private readonly TrustOrderStore $store,
        private readonly PasswordHasher $passwords,
    ) {
    }

    /** @return array<string, mixed> */
    public function login(string $email, string $password): array
    {
        $row = $this->store->findUserByEmail($email);
        if ($row === null || !$row['active'] || !$this->passwords->verify($password, $row['password'])) {
            throw new DomainException('E-mail ou mot de passe incorrect.', 401);
        }
        if ($row['role'] === 'SHOP' && ($row['boutique_id'] === null || $row['shop_active'] === false)) {
            throw new DomainException('Cette boutique est désactivée.', 403);
        }
        $this->store->audit($row['email'], 'LOGIN', 'Connexion Symfony.');

        return Actor::fromRow($row)->publicProfile();
    }
}
