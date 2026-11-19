<?php

declare(strict_types=1);

namespace App\Application;

use App\Domain\Exception\DomainException;
use App\Domain\Model\CustomerHistory;
use App\Domain\Port\TrustOrderStore;
use App\Domain\Service\PhoneNormalizer;
use App\Infrastructure\Scoring\FastApiClient;

final class CustomerQueryService
{
    public function __construct(
        private readonly TrustOrderStore $store,
        private readonly FastApiClient $engine,
        private readonly PhoneNormalizer $phones,
    ) {
    }

    /** @return array<string, mixed> */
    public function search(Actor $actor, string $rawPhone): array
    {
        $phone = $this->requirePhone($rawPhone);
        $hash = $this->hashOf($phone);
        $knownRow = $this->store->histories([$hash], (new \DateTimeImmutable('today'))->format('Y-m-d'));
        $known = isset($knownRow[$hash]);
        $history = $knownRow[$hash] ?? CustomerHistory::empty();
        $analysis = $this->engine->analyze($history, $hash);
        $customer = $this->store->findCustomerByHash($hash);
        $this->store->logAnalysis(
            $actor->shopId,
            $actor->email,
            $this->phones->mask($phone),
            $hash,
            'SEARCH',
            $analysis,
            null,
            sprintf('Recherche %s → %s/100 %s', $this->phones->mask($phone), $analysis['score'], $analysis['risk_level'])
        );

        return [
            'phone_mask' => $this->phones->mask($phone),
            'phone_full' => $actor->isAdmin() ? null : $phone,
            'known_customer' => $known,
            'customer' => $customer === null ? null : [
                'full_name' => $customer['full_name'],
                'city' => $customer['city'],
                'governorate' => $customer['governorate'],
            ],
            'history' => $history,
            'analysis' => $analysis,
            'shop_orders' => $this->store->ordersForPhone($hash, $actor->scope(), 20),
            'priority_if_new_order_amount_100' => $this->engine->prioritize($history, ['amount' => 100.0, 'order_id' => 'preview'], 'preview'),
            'engine' => EngineNote::forAnalysis($analysis),
            'cross_shop_note' => 'Les compteurs agrègent toutes les boutiques. Le détail des commandes des autres boutiques n\'est pas affiché.',
        ];
    }

    /** @param list<string> $phones
     *  @return array<string, mixed>
     */
    public function bulk(Actor $actor, array $phones): array
    {
        if ($phones === [] || count($phones) > 1000) {
            throw new DomainException('Entre 1 et 1000 numéros.');
        }
        $normalized = array_map(fn (string $phone) => $this->phones->normalize($phone), $phones);
        $valid = array_values(array_unique(array_filter($normalized)));
        $hashes = [];
        foreach ($valid as $phone) {
            $hashes[$phone] = $this->hashOf($phone);
        }
        $found = $this->store->histories(array_values($hashes), (new \DateTimeImmutable('today'))->format('Y-m-d'));
        $toAnalyze = [];
        foreach ($valid as $phone) {
            if (isset($found[$hashes[$phone]])) {
                $toAnalyze[] = ['customer_ref' => $phone, 'history' => $found[$hashes[$phone]]];
            }
        }
        $analyses = $toAnalyze === [] ? [] : $this->engine->analyzeMany($toAnalyze);
        $results = [];
        foreach ($phones as $index => $raw) {
            $tel = $normalized[$index];
            if ($tel === null) {
                $results[] = [
                    'input' => $raw, 'phone_mask' => null, 'result_type' => 'INVALID_NUMBER', 'orders' => 0,
                    'score' => null, 'risk_level' => null, 'cold_start' => null, 'retention_probability' => null,
                    'recommendation' => 'Numéro invalide : à corriger avant toute vérification.',
                ];
                continue;
            }
            $history = $found[$hashes[$tel]] ?? null;
            if ($history === null) {
                $results[] = [
                    'input' => $raw, 'phone_mask' => $this->phones->mask($tel), 'result_type' => 'UNKNOWN_CUSTOMER',
                    'orders' => 0, 'score' => null, 'risk_level' => 'UNKNOWN', 'cold_start' => true,
                    'retention_probability' => null,
                    'recommendation' => 'Aucun historique : traiter comme un nouveau client (confirmer la commande). La probabilité ML n\'est pas estimée.',
                ];
                continue;
            }
            $analysis = $analyses[$tel];
            $results[] = [
                'input' => $raw,
                'phone_mask' => $this->phones->mask($tel),
                'result_type' => 'ANALYZED',
                'orders' => CustomerHistory::settledOrders($history),
                'score' => $analysis['score'],
                'risk_level' => $analysis['risk_level'],
                'cold_start' => $analysis['cold_start'],
                'retention_probability' => $analysis['retention_probability'],
                'prediction_source' => $analysis['prediction_source'],
                'recommendation' => $analysis['recommendation'],
                'engine' => EngineNote::forAnalysis($analysis),
            ];
        }
        $summary = [
            'total' => count($results),
            'invalid_numbers' => count(array_filter($results, static fn (array $r) => $r['result_type'] === 'INVALID_NUMBER')),
            'unknown_customers' => count(array_filter($results, static fn (array $r) => $r['result_type'] === 'UNKNOWN_CUSTOMER')),
            'LOW' => count(array_filter($results, static fn (array $r) => ($r['risk_level'] ?? '') === 'LOW')),
            'MEDIUM' => count(array_filter($results, static fn (array $r) => ($r['risk_level'] ?? '') === 'MEDIUM')),
            'HIGH' => count(array_filter($results, static fn (array $r) => ($r['risk_level'] ?? '') === 'HIGH')),
        ];
        $this->store->audit($actor->email, 'BULK', 'Vérification en masse de '.count($results).' numéros.');

        return [
            'summary' => $summary,
            'results' => $results,
            'engine' => ['calculated_by' => 'moteur.analyser_client', 'live' => true],
        ];
    }

    /** @param array<string, mixed> $history
     *  @return array<string, mixed>
     */
    public function simulate(Actor $actor, array $history, float $amount): array
    {
        $clean = CustomerHistory::empty();
        foreach ($clean as $key => $_) {
            if (!isset($history[$key]) || !is_numeric($history[$key]) || (int) $history[$key] < 0) {
                throw new DomainException('Historique incomplet ou négatif : '.$key);
            }
            $clean[$key] = (int) $history[$key];
        }
        if ($amount <= 0) {
            throw new DomainException('Le montant doit être supérieur à 0.');
        }
        $analysis = $this->engine->analyze($clean, 'simulation');
        $priority = $this->engine->prioritize($clean, ['amount' => $amount, 'order_id' => 'simulation'], 'simulation');
        $this->store->logAnalysis($actor->shopId, $actor->email, 'simulation', 'simulation', 'SIMULATION', $analysis, $priority['priority'], $priority['explanation']);

        return [
            'history' => $clean,
            'analysis' => $analysis,
            'priority' => $priority,
            'engine' => EngineNote::forAnalysis($analysis),
            'warning' => 'Simulation : l\'historique est saisi à la main. Le résultat est calculé par le moteur, il ne provient pas d\'une commande réelle.',
        ];
    }

    /** @return array<string, mixed> */
    public function engineInfo(): array
    {
        $check = $this->engine->analyze(CustomerHistory::empty(), 'self-check');
        $settings = $this->engine->settings();
        $values = $settings['values'];

        return [
            'self_check_unknown_customer_score' => $check['score'],
            'self_check_expected' => 50,
            'self_check_ok' => $check['score'] === 50 && ($check['cold_start'] ?? false) === true,
            'model_version' => $check['model_version'] ?? null,
            'min_history' => $values['MIN_HISTORIQUE'],
            'risk_thresholds' => ['LOW' => $values['SEUIL_FAIBLE_RISQUE'], 'MEDIUM' => $values['SEUIL_RISQUE_MOYEN']],
            'priority_thresholds' => ['HIGH' => $values['SEUIL_PRIORITE_HAUTE'], 'MEDIUM' => $values['SEUIL_PRIORITE_MOYENNE']],
            'weights' => [
                'risk' => $values['POIDS_RISQUE'],
                'amount' => $values['POIDS_MONTANT'],
                'uncertainty' => $values['POIDS_INCERTITUDE'],
            ],
            'amount_cap_tnd' => $values['MONTANT_PLAFOND'],
            'formulas_modified' => false,
            'source_files' => ['service/scoring.py', 'service/moteur.py', 'service/ml.py', 'service/config.py'],
        ];
    }

    private function requirePhone(string $raw): string
    {
        $phone = $this->phones->normalize($raw);
        if ($phone === null) {
            throw new DomainException('Numéro tunisien invalide (8 chiffres).');
        }

        return $phone;
    }

    private function hashOf(string $phone): string
    {
        return (new \App\Domain\Service\PhoneHasher($this->secret()))->hash($phone);
    }

    private function secret(): string
    {
        return (string) ($_ENV['TRUSTORDER_SECRET'] ?? $_SERVER['TRUSTORDER_SECRET'] ?? 'dev-secret-a-changer-en-production');
    }
}
