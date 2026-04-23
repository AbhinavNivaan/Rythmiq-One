/**
 * Guards that the quarantined counterfeit crypto exports from
 * app-v2/services/security.ts do not return. See security audit S5.
 */

import * as securityModule from '../security';

describe('security.ts quarantine (S5)', () => {
  const BANNED_EXPORTS = [
    'sha256',
    'getRandomBytes',
    'generateSecureRandom',
    'hashValue',
    'verifyHash',
    'deriveMasterKey',
    'storeMasterKeyHash',
    'verifyMasterKey',
    'generateFileIntegrityHash',
    'verifyFileIntegrity',
  ] as const;

  it.each(BANNED_EXPORTS)('does not export %s', name => {
    expect((securityModule as Record<string, unknown>)[name]).toBeUndefined();
  });

  it('exports only SecureStore wrappers and biometric-flag helpers', () => {
    const exported = Object.keys(securityModule).sort();
    expect(exported).toEqual(
      [
        'STORAGE_KEYS',
        'isBiometricEnabled',
        'secureDelete',
        'secureRetrieve',
        'secureStore',
        'setBiometricEnabled',
      ].sort(),
    );
  });
});
