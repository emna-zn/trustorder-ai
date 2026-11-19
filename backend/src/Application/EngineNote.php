<?php

declare(strict_types=1);

namespace App\Application;

final class EngineNote
{
    /** @param array<string, mixed> $analysis
     *  @return array<string, mixed>
     */
    public static function forAnalysis(array $analysis): array
    {
        if (!empty($analysis['cold_start'])) {
            $prediction = "Cold start : le modèle ML n'a pas été appelé (historique insuffisant). Décision du moteur de règles.";
        } elseif (($analysis['retention_probability'] ?? null) === null) {
            $prediction = 'Probabilité ML absente.';
        } else {
            $prediction = 'Probabilité de rétention calculée par '.($analysis['model_version'] ?? 'le modèle')
                .' (régression logistique du Sprint 1).';
        }

        return [
            'calculated_by' => 'FastAPI /v1/analyze → service/moteur.py',
            'prediction_note' => $prediction,
            'demo_data' => true,
            'not_a_hardcoded_score' => true,
        ];
    }
}
