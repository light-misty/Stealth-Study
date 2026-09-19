export interface FindAvailablePortOptions {
  startPort?: number;
  host?: string;
  maxAttempts?: number;
  logger?: ((message: string) => void) | null;
}

export function isPortAvailable(port: number, host?: string): Promise<boolean>;
export function findAvailablePort(options?: FindAvailablePortOptions): Promise<number>;
