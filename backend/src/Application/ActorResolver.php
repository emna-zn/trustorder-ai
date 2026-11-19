<?php

declare(strict_types=1);

namespace App\Application;

use App\Domain\Exception\DomainException;
use App\Domain\Port\TrustOrderStore;
use Symfony\Bundle\SecurityBundle\Security;

final class ActorResolver
{
    public function __construct(private readonly Security $security, private readonly TrustOrderStore $store)
    {
    }

    public function current(): Actor
    {
        $user = $this->security->getUser();
        if ($user === null) {
            throw new DomainException('Connexion requise.', 401);
        }
        $row = $this->store->findUserByEmail($user->getUserIdentifier());
        if ($row === null || !$row['active']) {
            throw new DomainException('Compte inactif ou introuvable.', 401);
        }
        if ($row['role'] === 'SHOP' && ($row['boutique_id'] === null || $row['shop_active'] === false)) {
            throw new DomainException('Cette boutique est désactivée.', 403);
        }

        return Actor::fromRow($row);
    }
}
