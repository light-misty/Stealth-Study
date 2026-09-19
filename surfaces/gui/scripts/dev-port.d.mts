export interface FindAvailablePortOptions {
  startPort?: number;
  maxAttempts?: number;
  logger?: ((message: string) => void) | null;
}

export function isPortAvailable(port: number, hosts?: string[]): Promise<boolean>;
export function findAvailablePort(options?: FindAvailablePortOptions): Promise<number>;
export interface DevApiEndpoint {
  port: number;
  token: string;
}
export function findDevApi(stateDir: string): DevApiEndpoint | null;
