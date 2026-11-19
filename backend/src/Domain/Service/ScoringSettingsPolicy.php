<?php

declare(strict_types=1);

namespace App\Domain\Service;

use App\Domain\Exception\DomainException;

/**
 * Bornes des constantes autorisées. La formule elle-même reste dans scoring.py / moteur.py.
 */
final class ScoringSettingsPolicy
{
    /** @var array<string, array{0: string, 1: float, 2: float}> */
    public const SPEC = [
        'MIN_HISTORIQUE' => ['int', 1, 50],
        'SUCCES_IMAGINAIRES' => ['int', 0, 20],
        'ECHECS_IMAGINAIRES' => ['int', 0, 20],
        'PENALITE_ECHEC_RECENT' => ['int', 0, 50],
        'PENALITE_ECHEC_RECENT_MAX' => ['int', 0, 100],
        'PENALITE_SIGNALEMENT' => ['int', 0, 50],
        'PENALITE_SIGNALEMENT_MAX' => ['int', 0, 100],
        'PENALITE_MULTI_BOUTIQUES' => ['int', 0, 50],
        'BONUS_FIDELITE' => ['int', 0, 30],
        'FIDELITE_MIN_LIVREES' => ['int', 1, 100],
        'FIDELITE_TAUX_ECHEC_MAX' => ['float', 0, 1],
        'SEUIL_FAIBLE_RISQUE' => ['int', 0, 100],
        'SEUIL_RISQUE_MOYEN' => ['int', 0, 100],
        'POIDS_RISQUE' => ['float', 0, 1],
        'POIDS_MONTANT' => ['float', 0, 1],
        'POIDS_INCERTITUDE' => ['float', 0, 1],
        'MONTANT_PLAFOND' => ['int', 1, 100000],
        'SEUIL_PRIORITE_HAUTE' => ['int', 0, 100],
        'SEUIL_PRIORITE_MOYENNE' => ['int', 0, 100],
    ];

    /** @param array<string, mixed> $payload
     *  @return array<string, int|float>
     */
    public function validate(array $payload): array
    {
        $clean = [];
        foreach ($payload as $key => $raw) {
            if (!isset(self::SPEC[$key])) {
                throw new DomainException('Paramètre non autorisé : '.$key);
            }
            [$kind, $lo, $hi] = self::SPEC[$key];
            if (is_bool($raw) || !is_numeric($raw)) {
                throw new DomainException('Valeur invalide pour '.$key);
            }
            $value = $kind === 'int' ? (int) $raw : (float) $raw;
            if ($kind === 'int' && (float) $value !== (float) $raw) {
                throw new DomainException('Valeur invalide pour '.$key);
            }
            if ($value < $lo || $value > $hi) {
                throw new DomainException(sprintf('%s hors limites (%s–%s)', $key, $lo, $hi));
            }
            $clean[$key] = $value;
        }

        return $clean;
    }

    /** @param array<string, int|float> $merged */
    public function assertConsistent(array $merged): void
    {
        if (($merged['SEUIL_FAIBLE_RISQUE'] ?? 0) < ($merged['SEUIL_RISQUE_MOYEN'] ?? 0)) {
            throw new DomainException('Le seuil LOW doit être supérieur ou égal au seuil MEDIUM.');
        }
        if (($merged['SEUIL_PRIORITE_HAUTE'] ?? 0) < ($merged['SEUIL_PRIORITE_MOYENNE'] ?? 0)) {
            throw new DomainException('Le seuil de priorité haute doit être supérieur ou égal au seuil moyen.');
        }
        $poids = (float) ($merged['POIDS_RISQUE'] ?? 0) + (float) ($merged['POIDS_MONTANT'] ?? 0) + (float) ($merged['POIDS_INCERTITUDE'] ?? 0);
        if (abs($poids - 1) > 0.001) {
            throw new DomainException('La somme des poids de priorité doit rester égale à 1.');
        }
    }
}
