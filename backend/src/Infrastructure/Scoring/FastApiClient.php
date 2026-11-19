<?php

declare(strict_types=1);

namespace App\Infrastructure\Scoring;

use App\Domain\Exception\DomainException;
use Symfony\Component\Mime\Part\DataPart;
use Symfony\Component\Mime\Part\Multipart\FormDataPart;
use Symfony\Contracts\HttpClient\HttpClientInterface;

/**
 * Seul passage vers le service Python. Aucun score n'est calculé dans PHP.
 */
final class FastApiClient
{
    public function __construct(
        private readonly HttpClientInterface $http,
        private readonly string $baseUrl,
        private readonly string $token,
    ) {
    }

    /** @param array<string, int> $history */
    public function analyze(array $history, ?string $ref = null): array
    {
        return $this->json('POST', '/v1/analyze', [
            'customer_ref' => $ref,
            'history' => $history,
        ]);
    }

    /**
     * @param list<array{customer_ref: string, history: array<string, int>}> $items
     * @return array<string, array<string, mixed>>
     */
    public function analyzeMany(array $items): array
    {
        $indexed = [];
        foreach (array_chunk($items, 400) as $chunk) {
            $payload = $this->json('POST', '/v1/analyze/batch', ['items' => $chunk]);
            foreach ($payload['results'] as $result) {
                $indexed[(string) $result['customer_ref']] = $result;
            }
        }

        return $indexed;
    }

    /** @param array<string, int> $history
     *  @param array{order_id?: string, amount: float} $order
     */
    public function prioritize(array $history, array $order, ?string $ref = null): array
    {
        return $this->json('POST', '/v1/prioritize', [
            'customer_ref' => $ref,
            'history' => $history,
            'order' => $order,
        ]);
    }

    /**
     * @param list<array{customer_ref: string, history: array<string, int>, order: array{order_id: string, amount: float}}> $items
     * @return array<string, array<string, mixed>>
     */
    public function prioritizeMany(array $items): array
    {
        $indexed = [];
        foreach (array_chunk($items, 400) as $chunk) {
            $payload = $this->json('POST', '/v1/prioritize/batch', ['items' => $chunk]);
            foreach ($payload['results'] as $result) {
                $indexed[(string) ($result['customer_ref'] ?? $result['order_id'])] = $result;
            }
        }

        return $indexed;
    }

    public function settings(): array
    {
        return $this->json('GET', '/v1/settings');
    }

    /** @param array<string, int|float> $values */
    public function putSettings(array $values): array
    {
        return $this->json('PUT', '/v1/settings', $values, true);
    }

    public function resetSettings(): array
    {
        return $this->json('POST', '/v1/settings/reset', null, true);
    }

    public function importFile(int $shopId, string $filename, string $bytes): array
    {
        return $this->upload('/v2/import/fichier', $shopId, $filename, $bytes);
    }

    public function importDocument(int $shopId, string $filename, string $bytes): array
    {
        return $this->upload('/v2/import/document', $shopId, $filename, $bytes);
    }

    public function getLot(string $lotId): array
    {
        return $this->json('GET', '/v2/lots/'.rawurlencode($lotId));
    }

    /** @param array<string, mixed> $patch */
    public function patchLine(string $lotId, int $line, array $patch): array
    {
        return $this->json('PATCH', '/v2/lots/'.rawurlencode($lotId).'/lignes/'.$line, $patch);
    }

    public function validateLot(string $lotId): array
    {
        return $this->json('POST', '/v2/lots/'.rawurlencode($lotId).'/valider');
    }

    /** @return list<string> */
    public function extractPhones(string $filename, string $bytes): array
    {
        $payload = $this->upload('/v2/outils/numeros', null, $filename, $bytes);

        return $payload['phones'] ?? [];
    }

    /** @param array<string, mixed>|null $json */
    private function json(string $method, string $path, ?array $json = null, bool $internal = false): array
    {
        $options = ['timeout' => 60, 'headers' => $internal ? $this->tokenHeader() : []];
        if ($json !== null) {
            $options['json'] = $json;
        }
        try {
            $response = $this->http->request($method, $this->url($path), $options);
            $status = $response->getStatusCode();
            $data = $response->toArray(false);
        } catch (\Throwable $e) {
            throw new DomainException('Service IA injoignable ('.$e->getMessage().').', 503);
        }

        return $this->assertOk($status, $data);
    }

    private function upload(string $path, ?int $shopId, string $filename, string $bytes): array
    {
        $fields = ['fichier' => new DataPart($bytes, $filename)];
        if ($shopId !== null) {
            $fields = ['boutique_id' => (string) $shopId] + $fields;
        }
        $form = new FormDataPart($fields);
        $headers = $form->getPreparedHeaders()->toArray();
        try {
            $response = $this->http->request('POST', $this->url($path), [
                'headers' => $headers,
                'body' => $form->bodyToIterable(),
                'timeout' => 60,
            ]);
            $status = $response->getStatusCode();
            $data = $response->toArray(false);
        } catch (\Throwable $e) {
            throw new DomainException('Service IA injoignable ('.$e->getMessage().').', 503);
        }

        return $this->assertOk($status, $data);
    }

    /** @param array<string, mixed> $data */
    private function assertOk(int $status, array $data): array
    {
        if ($status >= 400) {
            $detail = $data['detail'] ?? 'Le service IA a refusé la demande.';
            if (!is_string($detail)) {
                $detail = json_encode($detail, JSON_UNESCAPED_UNICODE) ?: 'Erreur du service IA.';
            }
            throw new DomainException($detail, $status >= 500 ? 503 : $status);
        }

        return $data;
    }

    /** @return array<string, string> */
    private function tokenHeader(): array
    {
        return $this->token === '' ? [] : ['X-Internal-Token' => $this->token];
    }

    private function url(string $path): string
    {
        return rtrim($this->baseUrl, '/').$path;
    }
}
