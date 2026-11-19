<?php

declare(strict_types=1);

namespace App\Application;

final class Actor
{
    public function __construct(
        public readonly int $id,
        public readonly string $email,
        public readonly string $fullName,
        public readonly string $role,
        public readonly ?int $shopId,
        public readonly ?string $shopName,
        public readonly ?string $shopCity,
        public readonly ?string $shopGovernorate,
    ) {
    }

    public function isAdmin(): bool
    {
        return $this->role === 'ADMIN';
    }

    public function scope(): ?int
    {
        return $this->isAdmin() ? null : $this->shopId;
    }

    /** @param array<string, mixed> $row */
    public static function fromRow(array $row): self
    {
        return new self(
            $row['id'],
            $row['email'],
            $row['full_name'],
            $row['role'],
            $row['boutique_id'],
            $row['shop_name'],
            $row['shop_city'],
            $row['shop_governorate'],
        );
    }

    /** @return array<string, mixed> */
    public function publicProfile(): array
    {
        return [
            'id' => $this->id,
            'email' => $this->email,
            'full_name' => $this->fullName,
            'role' => $this->role,
            'boutique_id' => $this->shopId,
            'shop' => $this->shopId === null ? null : [
                'id' => $this->shopId,
                'name' => $this->shopName,
                'city' => $this->shopCity,
                'governorate' => $this->shopGovernorate,
                'active' => true,
            ],
        ];
    }
}
