import { createContext, useContext, useState, type ReactNode } from 'react';

// The customer (client company) whose documents the clerk is working on.
// Every upload and every list is scoped to it. Remembered in this browser.

const STORAGE_KEY = 'docuflow.customer';
export const CUSTOMER_ID_RE = /^[a-z0-9_-]{1,64}$/;

function readStored(): string {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v && CUSTOMER_ID_RE.test(v) ? v : 'default';
  } catch {
    return 'default';
  }
}

interface CustomerState {
  customer: string;
  setCustomer: (id: string) => void;
}

const CustomerContext = createContext<CustomerState>({ customer: 'default', setCustomer: () => {} });

export function CustomerProvider({ children }: { children: ReactNode }) {
  const [customer, setState] = useState<string>(readStored);
  const setCustomer = (id: string) => {
    setState(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* private mode: keep it for this session only */
    }
  };
  return <CustomerContext.Provider value={{ customer, setCustomer }}>{children}</CustomerContext.Provider>;
}

export function useCustomer(): CustomerState {
  return useContext(CustomerContext);
}
