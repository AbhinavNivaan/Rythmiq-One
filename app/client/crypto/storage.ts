import { InvalidInputError } from "./errors";

// NOT SECURE PERSISTENCE - in-memory only
const store = new Map<string, Uint8Array>();
const keyStore = new Map<string, CryptoKey>();

export function storeKey(id: string, key: Uint8Array): void {
  if (!id) {
    throw new InvalidInputError("Key ID must not be empty");
  }
  if (key === null || key === undefined) {
    throw new InvalidInputError("Key must not be null or undefined");
  }
  if (!(key instanceof Uint8Array)) {
    throw new InvalidInputError("Key must be a Uint8Array");
  }
  store.set(id, key);
}

export function retrieveKey(id: string): Uint8Array | undefined {
  if (!id) {
    throw new InvalidInputError("Key ID must not be empty");
  }
  return store.get(id);
}

export function deleteKey(id: string): boolean {
  if (!id) {
    throw new InvalidInputError("Key ID must not be empty");
  }
  return store.delete(id);
}

export function storeCryptoKey(id: string, key: CryptoKey): void {
  if (!id) {
    throw new InvalidInputError("Key ID must not be empty");
  }
  if (key === null || key === undefined) {
    throw new InvalidInputError("CryptoKey must not be null or undefined");
  }
  keyStore.set(id, key);
}

export function retrieveCryptoKey(id: string): CryptoKey | undefined {
  if (!id) {
    throw new InvalidInputError("Key ID must not be empty");
  }
  return keyStore.get(id);
}

export function deleteCryptoKey(id: string): boolean {
  if (!id) {
    throw new InvalidInputError("Key ID must not be empty");
  }
  return keyStore.delete(id);
}

export function persistToDisk(): never {
  throw new Error("Persistent storage is not implemented");
}
