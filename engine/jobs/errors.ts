export type ProcessingStage = 'OCR' | 'NORMALIZE' | 'TRANSFORM';

export interface ProcessingError {
  code: string;
  retryable: boolean;
  stage: ProcessingStage;
}
