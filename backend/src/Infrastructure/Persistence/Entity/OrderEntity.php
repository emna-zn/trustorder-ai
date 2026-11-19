<?php

declare(strict_types=1);

namespace App\Infrastructure\Persistence\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(
    name: 'customer_order',
    uniqueConstraints: [new ORM\UniqueConstraint(name: 'uniq_order_fingerprint', columns: ['fingerprint'])],
    indexes: [
        new ORM\Index(name: 'idx_order_phone', columns: ['phone_hash', 'status', 'order_date']),
        new ORM\Index(name: 'idx_order_shop', columns: ['boutique_id', 'order_date']),
    ]
)]
class OrderEntity
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    public ?int $id = null;

    #[ORM\ManyToOne(targetEntity: ShopEntity::class)]
    #[ORM\JoinColumn(name: 'boutique_id', nullable: false, onDelete: 'CASCADE')]
    public ShopEntity $boutique;

    #[ORM\ManyToOne(targetEntity: CustomerEntity::class)]
    #[ORM\JoinColumn(name: 'customer_id', nullable: false, onDelete: 'CASCADE')]
    public CustomerEntity $customer;

    #[ORM\Column(name: 'phone_hash', length: 64)]
    public string $phoneHash = '';

    #[ORM\Column(length: 255)]
    public string $label = '';

    #[ORM\Column(type: 'decimal', precision: 10, scale: 3, nullable: true)]
    public ?string $amount = null;

    #[ORM\Column(length: 20)]
    public string $status = 'PENDING';

    #[ORM\Column(name: 'order_date', type: 'date_immutable')]
    public \DateTimeImmutable $orderDate;

    #[ORM\Column(length: 64)]
    public string $fingerprint = '';

    #[ORM\Column(name: 'created_at')]
    public \DateTimeImmutable $createdAt;

    public function __construct()
    {
        $this->orderDate = new \DateTimeImmutable('today');
        $this->createdAt = new \DateTimeImmutable();
    }
}
