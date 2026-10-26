/**
 * Tiny promise wrapper over IndexedDB. One database, shared with the service worker (public/sw.js opens the same
 * name/version/stores to receive Android share-sheet uploads), so the three stores below must stay in sync with sw.js.
 *
 *   queue    offline writes waiting to be replayed (urge captures, check-ins)
 *   share    the one pending Android share-sheet payload (text and/or one image)
 *   snapshot the last check-in view per user and day, so the check-in can open with no signal
 */
export const DB_NAME = 'lockin-offline';
export const DB_VERSION = 1;
export type StoreName = 'queue' | 'share' | 'snapshot';
const STORES: StoreName[] = ['queue', 'share', 'snapshot'];

let dbPromise: Promise<IDBDatabase> | null = null;

function open(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB is not available'));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const name of STORES) {
        if (!db.objectStoreNames.contains(name)) db.createObjectStore(name, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => {
      const db = req.result;
      db.onversionchange = () => {
        db.close();
        dbPromise = null;
      };
      resolve(db);
    };
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'));
    req.onblocked = () => reject(new Error('IndexedDB open blocked'));
  }).catch((err) => {
    dbPromise = null; // let the next call try again
    throw err;
  });
  return dbPromise;
}

async function run<T>(store: StoreName, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const req = fn(tx.objectStore(store));
    let result: T;
    req.onsuccess = () => {
      result = req.result;
    };
    tx.oncomplete = () => resolve(result);
    tx.onerror = () => reject(tx.error ?? req.error);
    tx.onabort = () => reject(tx.error ?? new Error('IndexedDB transaction aborted'));
  });
}

export const idbGet = <T>(store: StoreName, id: string) =>
  run<T | undefined>(store, 'readonly', (s) => s.get(id) as IDBRequest<T | undefined>);
export const idbAll = <T>(store: StoreName) => run<T[]>(store, 'readonly', (s) => s.getAll() as IDBRequest<T[]>);
export const idbPut = <T extends { id: string }>(store: StoreName, value: T) =>
  run<IDBValidKey>(store, 'readwrite', (s) => s.put(value));
export const idbDelete = (store: StoreName, id: string) => run<undefined>(store, 'readwrite', (s) => s.delete(id));
export const idbClear = (store: StoreName) => run<undefined>(store, 'readwrite', (s) => s.clear());
