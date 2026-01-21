export class InvalidInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidInputError";
    Object.setPrototypeOf(this, InvalidInputError.prototype);
  }
}

export class UnsupportedVersionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnsupportedVersionError";
    Object.setPrototypeOf(this, UnsupportedVersionError.prototype);
  }
}

export class CryptoOperationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CryptoOperationError";
    Object.setPrototypeOf(this, CryptoOperationError.prototype);
  }
}
