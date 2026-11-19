<?php

declare(strict_types=1);

namespace App\Infrastructure\Persistence\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'app_user', uniqueConstraints: [new ORM\UniqueConstraint(name: 'uniq_user_email', columns: ['email'])])]
class UserEntity
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    public ?int $id = null;

    #[ORM\Column(length: 180)]
    public string $email = '';

    #[ORM\Column(length: 255)]
    public string $password = '';

    #[ORM\Column(name: 'full_name', length: 120)]
    public string $fullName = '';

    #[ORM\Column(length: 16)]
    public string $role = 'SHOP';

    #[ORM\ManyToOne(targetEntity: ShopEntity::class)]
    #[ORM\JoinColumn(name: 'boutique_id', nullable: true, onDelete: 'SET NULL')]
    public ?ShopEntity $boutique = null;

    #[ORM\Column]
    public bool $active = true;
}
