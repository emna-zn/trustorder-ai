<?php

declare(strict_types=1);

namespace App\Infrastructure\Persistence\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'score_setting')]
class SettingEntity
{
    #[ORM\Id]
    #[ORM\Column(length: 64)]
    public string $settingKey = '';

    #[ORM\Column(length: 32)]
    public string $value = '';
}
