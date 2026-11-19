<?php

declare(strict_types=1);

namespace App\Infrastructure\Persistence\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'analysis_log')]
class AnalysisEntity
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    public ?int $id = null;

    #[ORM\Column(name: 'boutique_id', nullable: true)]
    public ?int $boutiqueId = null;

    #[ORM\Column(name: 'actor_email', length: 180)]
    public string $actorEmail = '';

    #[ORM\Column(name: 'phone_mask', length: 32)]
    public string $phoneMask = '';

    #[ORM\Column(name: 'phone_hash', length: 64)]
    public string $phoneHash = '';

    #[ORM\Column(length: 20)]
    public string $kind = '';

    #[ORM\Column(nullable: true)]
    public ?int $score = null;

    #[ORM\Column(name: 'risk_level', length: 16, nullable: true)]
    public ?string $riskLevel = null;

    #[ORM\Column(length: 16, nullable: true)]
    public ?string $priority = null;

    #[ORM\Column(name: 'cold_start')]
    public bool $coldStart = false;

    #[ORM\Column(name: 'retention_probability', type: 'float', nullable: true)]
    public ?float $retentionProbability = null;

    #[ORM\Column(name: 'prediction_source', length: 20)]
    public string $predictionSource = 'RULES';

    #[ORM\Column(length: 500)]
    public string $summary = '';

    #[ORM\Column(name: 'created_at')]
    public \DateTimeImmutable $createdAt;

    public function __construct()
    {
        $this->createdAt = new \DateTimeImmutable();
    }
}
