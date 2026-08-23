declare module "three" {
  const THREE: any;
  export = THREE;
}

declare module "zustand" {
  type StoreHook<T> = {
    <U>(selector: (state: T) => U): U;
    getState: () => T;
  };

  export function create<T>(initializer: (set: (partial: Partial<T>) => void) => T): StoreHook<T>;
}
