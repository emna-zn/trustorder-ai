<?php

declare(strict_types=1);

namespace App\Infrastructure\Persistence\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'boutique')]
class ShopEntity
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    public ?int $id = null;

    #[ORM\Column(length: 160)]
    public string $name = '';

    #[ORM\Column(length: 80)]
    public string $governorate = '';

    #[ORM\Column(length: 80)]
    public string $city = '';

    #[ORM\Column(length: 255)]
    public string $address = '';

    #[ORM\Column]
    public bool $active = true;

    #[ORM\Column(name: 'created_at')]
    public \DateTimeImmutable $createdAt;

    public function __construct()
    {
        $this->createdAt = new \DateTimeImmutable();
    }
}
