export type BoletoStatus = "Pendente" | "Pago" | "Atrasado";

export interface Boleto {
  id: string;
  beneficiario: string;
  categoria: string;
  valor: number;
  vencimento: string; // ISO
  status: BoletoStatus;
  linhaDigitavel: string;
}

export const sampleBoletos: Boleto[] = [
  {
    id: "blt_01",
    beneficiario: "ENEL Distribuição SP",
    categoria: "Conta de Luz",
    valor: 287.43,
    vencimento: "2026-05-02",
    status: "Pendente",
    linhaDigitavel: "83680000001 2 87430000000 0 12345678901 4 23456789012 5",
  },
  {
    id: "blt_02",
    beneficiario: "Vivo Fibra",
    categoria: "Internet",
    valor: 129.9,
    vencimento: "2026-04-27",
    status: "Pendente",
    linhaDigitavel: "23790123456 7 89012345678 9 01234567890 1 23456789012 3",
  },
  {
    id: "blt_03",
    beneficiario: "Amazon Web Services",
    categoria: "Cloud / Infra",
    valor: 1842.16,
    vencimento: "2026-05-10",
    status: "Pendente",
    linhaDigitavel: "00190500954 0 14816060680 9 35687170026 0 00000018421 6",
  },
  {
    id: "blt_04",
    beneficiario: "Sabesp",
    categoria: "Conta de Água",
    valor: 92.5,
    vencimento: "2026-04-22",
    status: "Atrasado",
    linhaDigitavel: "82660000000 9 92500000000 1 11122233344 5 55566677788 9",
  },
  {
    id: "blt_05",
    beneficiario: "Cloudflare Inc.",
    categoria: "Cloud / Infra",
    valor: 320.0,
    vencimento: "2026-04-15",
    status: "Pago",
    linhaDigitavel: "00193373700 0 00001000500 0 09402100114 0 00000003200 0",
  },
  {
    id: "blt_06",
    beneficiario: "Google Workspace",
    categoria: "SaaS",
    valor: 215.4,
    vencimento: "2026-05-05",
    status: "Pendente",
    linhaDigitavel: "00191234500 0 00021540000 1 23456789012 3 45678901234 5",
  },
  {
    id: "blt_07",
    beneficiario: "Comgás",
    categoria: "Conta de Gás",
    valor: 78.22,
    vencimento: "2026-04-27",
    status: "Pendente",
    linhaDigitavel: "82680000000 1 78220000000 9 99988877766 6 55544433322 1",
  },
  {
    id: "blt_08",
    beneficiario: "GitHub Enterprise",
    categoria: "SaaS",
    valor: 462.0,
    vencimento: "2026-04-10",
    status: "Pago",
    linhaDigitavel: "00198765400 0 00046200000 1 87654321098 7 65432109876 5",
  },
];

export function formatBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("pt-BR");
}

export function isToday(iso: string) {
  const d = new Date(iso + "T00:00:00");
  const t = new Date();
  return d.getDate() === t.getDate() && d.getMonth() === t.getMonth() && d.getFullYear() === t.getFullYear();
}
