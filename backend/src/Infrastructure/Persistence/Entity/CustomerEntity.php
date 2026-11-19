<?php

declare(strict_types=1);

namespace App\Infrastructure\Persistence\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'customer', uniqueConstraints: [
    new ORM\UniqueConstraint(name: 'uniq_customer_phone', columns: ['phone_normalized']),
    new ORM\UniqueConstraint(name: 'uniq_customer_hash', columns: ['phone_hash']),
])]
class CustomerEntity
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    public ?int $id = null;

    #[ORM\Column(name: 'full_name', length: 160)]
    public string $fullName = '';

    #[ORM\Column(name: 'phone_normalized', length: 20)]
    public string $phoneNormalized = '';

    #[ORM\Column(name: 'phone_hash', length: 64)]
    public string $phoneHash = '';

    #[ORM\Column(name: 'phone_mask', length: 32)]
    public string $phoneMask = '';

    #[ORM\Column(length: 80)]
    public string $governorate = '';

    #[ORM\Column(length: 80)]
    public string $city = '';
}
