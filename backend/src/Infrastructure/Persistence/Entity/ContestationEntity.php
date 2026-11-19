<?php

declare(strict_types=1);

namespace App\Infrastructure\Persistence\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'contestation')]
class ContestationEntity
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    public ?int $id = null;

    #[ORM\ManyToOne(targetEntity: ShopEntity::class)]
    #[ORM\JoinColumn(name: 'boutique_id', nullable: false, onDelete: 'CASCADE')]
    public ShopEntity $boutique;

    #[ORM\Column(name: 'phone_hash', length: 64)]
    public string $phoneHash = '';

    #[ORM\Column(name: 'phone_mask', length: 32)]
    public string $phoneMask = '';

    #[ORM\Column(length: 255)]
    public string $motif = '';

    #[ORM\Column(length: 20)]
    public string $status = 'EN_ATTENTE';

    #[ORM\Column(name: 'decision_note', length: 255, nullable: true)]
    public ?string $decisionNote = null;

    #[ORM\Column(name: 'created_at')]
    public \DateTimeImmutable $createdAt;

    #[ORM\Column(name: 'updated_at')]
    public \DateTimeImmutable $updatedAt;

    public function __construct()
    {
        $this->createdAt = new \DateTimeImmutable();
        $this->updatedAt = new \DateTimeImmutable();
    }
}
