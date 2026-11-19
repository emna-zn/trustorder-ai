<?php

declare(strict_types=1);

namespace App\Domain\Service;

/**
 * Même contrat que service/telephone.py : un numéro tunisien devient 216XXXXXXXX, sinon null.
 */
final class PhoneNormalizer
{
    public function normalize(mixed $value): ?string
    {
        if ($value === null) {
            return null;
        }
        if (is_float($value) && floor($value) === $value) {
            $value = (int) $value;
        }
        $text = preg_replace('/\.0+$/', '', trim((string) $value)) ?? '';
        $digits = preg_replace('/\D+/', '', $text) ?? '';
        if (str_starts_with($digits, '00216')) {
            $digits = substr($digits, 2);
        }
        if (strlen($digits) === 8) {
            $digits = '216'.$digits;
        }
        if (preg_match('/^216[2-9]\d{7}$/', $digits) === 1) {
            return $digits;
        }

        return null;
    }

    public function mask(string $normalized): string
    {
        $local = substr($normalized, 3);

        return sprintf('+216 %s *** %s', substr($local, 0, 2), substr($local, -3));
    }
}
