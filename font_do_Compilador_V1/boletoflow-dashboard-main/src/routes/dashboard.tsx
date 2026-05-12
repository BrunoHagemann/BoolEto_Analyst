import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState, useCallback } from "react";
import {
  UploadCloud,
  TrendingDown,
  CalendarDays,
  Wallet,
  Copy,
  Search,
  CheckCircle2,
  Clock,
  AlertTriangle,
  X,
  RefreshCw,
  Loader2,
  Mail,
  Check,
  Eye,
} from "lucide-react";
import { Header } from "@/components/Header";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatBRL, formatDate, isToday, type BoletoStatus } from "@/lib/boletos";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — BoolEto" },
      { name: "description", content: "Gerencie, processe e acompanhe seus boletos em tempo real." },
    ],
  }),
  component: DashboardPage,
});

// =====================================================================
// 🔌 INTEGRAÇÃO COM O BACK-END PYTHON (COMPILADOR .BOOL)
// =====================================================================
const API_BASE = import.meta.env.VITE_BOOLETO_API_URL || "http://localhost:5000";

// Interface local ajustada para suportar a URL da imagem e os campos editáveis
interface BoletoLocal {
  id: number;
  beneficiario: string;
  categoria: string;
  vencimento: string;
  valor: number;
  status: BoletoStatus;
  linhaDigitavel: string;
  url_imagem?: string | null;
}

async function fetchBoletos(): Promise<BoletoLocal[]> {
  const res = await fetch(`${API_BASE}/boletos`);
  if (!res.ok) throw new Error(`Falha ao buscar boletos (${res.status})`);
  return (await res.json()) as BoletoLocal[];
}

async function uploadBoleto(file: File): Promise<BoletoLocal> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/boletos/process`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`Falha no processamento (${res.status})`);
  return (await res.json()) as BoletoLocal;
}

async function confirmarPagamentoApi(id: string | number): Promise<void> {
  const res = await fetch(`${API_BASE}/boletos/pay/${id}`, { method: "POST" });
  if (!res.ok) throw new Error("Erro ao confirmar pagamento");
}

async function dispararEmailsApi(): Promise<void> {
  const res = await fetch(`${API_BASE}/boletos/check`, { method: "POST" });
  if (!res.ok) throw new Error("Erro ao disparar notificações de e-mail");
}

// NOVA FUNÇÃO: Envia a edição de Nome e Categoria para o Python salvar no banco
async function atualizarBoletoApi(id: string | number, nome: string, categoria: string): Promise<void> {
  const res = await fetch(`${API_BASE}/boletos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nome, categoria }),
  });
  if (!res.ok) throw new Error("Erro ao salvar edições");
}

function statusBadge(s: BoletoStatus) {
  if (s === "Pago")
    return (
      <Badge className="gap-1 bg-success/15 text-success border border-success/30 hover:bg-success/15">
        <CheckCircle2 className="h-3 w-3" /> Pago
      </Badge>
    );
  if (s === "Atrasado")
    return (
      <Badge className="gap-1 bg-destructive/15 text-destructive border border-destructive/30 hover:bg-destructive/15">
        <AlertTriangle className="h-3 w-3" /> Atrasado
      </Badge>
    );
  return (
    <Badge className="gap-1 bg-warning/15 text-warning border border-warning/30 hover:bg-warning/15">
      <Clock className="h-3 w-3" /> Pendente
    </Badge>
  );
}

function DashboardPage() {
  const [boletos, setBoletos] = useState<BoletoLocal[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [checkingEmails, setCheckingEmails] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [dragOver, setDragOver] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBoletos();
      setBoletos(Array.isArray(data) ? data : []);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erro ao carregar dados do servidor Python.";
      setError(msg);
      setBoletos([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // AÇÃO DE PAGAR
  const handlePagar = async (id: number, nome: string) => {
    try {
      await confirmarPagamentoApi(id);
      setBoletos((prev) =>
        prev.map((b) => (b.id === id ? { ...b, status: "Pago" as BoletoStatus } : b))
      );
      toast.success("Pagamento confirmado!", { description: `Baixa efetuada para: ${nome}` });
    } catch (e) {
      toast.error("Falha ao processar pagamento no banco de dados.");
    }
  };

  // AÇÃO DE EDITAR: Disparada automaticamente ao sair do input (onBlur)
  const handleSalvarEdicao = async (id: number, novoNome: string, novaCategoria: string) => {
    try {
      await atualizarBoletoApi(id, novoNome, novaCategoria);
      setBoletos((prev) =>
        prev.map((b) => (b.id === id ? { ...b, beneficiario: novoNome, categoria: novaCategoria } : b))
      );
      toast.success("Edição salva com sucesso!");
    } catch (e) {
      toast.error("Erro ao atualizar os dados no banco SQLite.");
    }
  };

  // AÇÃO DE NOTIFICAR
  const handleNotificar = async () => {
    setCheckingEmails(true);
    try {
      await dispararEmailsApi();
      toast.success("Varredura concluída!", { description: "E-mails enviados para boletos próximos do vencimento." });
    } catch (e) {
      toast.error("Erro ao conectar com o sistema de e-mails (SMTP).");
    } finally {
      setCheckingEmails(false);
    }
  };

  const stats = useMemo(() => {
    const totalMes = boletos.filter((b) => b.status !== "Pago").reduce((a, b) => a + b.valor, 0);
    const vencendoHoje = boletos.filter((b) => b.status !== "Pago" && isToday(b.vencimento)).length;
    const pagos = boletos.filter((b) => b.status === "Pago").reduce((a, b) => a + b.valor, 0);
    return { totalMes, vencendoHoje, pagos };
  }, [boletos]);

  const filtered = useMemo(() => {
    if (!query.trim()) return boletos;
    const q = query.toLowerCase();
    return boletos.filter(
      (b) =>
        b.beneficiario.toLowerCase().includes(q) ||
        b.categoria.toLowerCase().includes(q) ||
        b.linhaDigitavel.includes(q),
    );
  }, [boletos, query]);

  const chartData = useMemo(() => {
    const map = new Map<string, number>();
    boletos.forEach((b) => map.set(b.categoria, (map.get(b.categoria) ?? 0) + b.valor));
    return Array.from(map.entries()).map(([categoria, total]) => ({
      categoria,
      total: Number(total.toFixed(2)),
    }));
  }, [boletos]);

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const accepted = Array.from(files).filter((f) =>
      ["application/pdf", "image/png", "image/jpeg", "image/webp"].includes(f.type),
    );
    if (accepted.length === 0) {
      toast.error("Formato não suportado. Envie PDF, PNG ou JPG.");
      return;
    }
    setUploading(true);
    try {
      for (const file of accepted) {
        try {
          const novo = await uploadBoleto(file);
          setBoletos((prev) => [novo, ...prev]);
          toast.success("Boleto digitalizado via IA!", { description: "Clique no nome ou categoria na tabela para personalizar." });
        } catch (e) {
          const msg = e instanceof Error ? e.message : "Falha na leitura OCR";
          toast.error(`${file.name}: ${msg}`);
        }
      }
    } finally {
      setUploading(false);
    }
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <div className="mx-auto max-w-7xl space-y-8 px-4 py-8 md:px-6 md:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">Dashboard</h1>
            <p className="text-sm text-muted-foreground">Conectado ao motor de IA (EasyOCR & SQLite).</p>
          </div>
          
          {/* BOTÕES DE AÇÃO SUPERIORES */}
          <div className="flex items-center gap-2">
            <Button 
              variant="default" 
              size="sm" 
              className="bg-primary hover:bg-primary/90"
              onClick={handleNotificar} 
              disabled={checkingEmails || loading}
            >
              {checkingEmails ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Mail className="mr-2 h-4 w-4" />}
              Disparar Alertas
            </Button>

            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              Atualizar
            </Button>
          </div>
        </div>

        {error && (
          <Card className="border-destructive/40 bg-destructive/5">
            <CardContent className="p-4 text-sm text-destructive">
              <p className="font-bold">⚠️ Servidor Python Offline</p>
              <p className="mt-1">{error}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                Certifique-se de que a API local está rodando na porta 5000 antes de enviar imagens ou pagamentos.
              </p>
            </CardContent>
          </Card>
        )}

        {/* ANALYTICS */}
        <div className="grid gap-4 md:grid-cols-3">
          <StatCard icon={Wallet} label="Total a Pagar" value={formatBRL(stats.totalMes)} accent="primary" loading={loading} />
          <StatCard icon={CalendarDays} label="Vencendo Hoje" value={String(stats.vencendoHoje)} accent="violet" loading={loading} />
          <StatCard icon={TrendingDown} label="Total Pago" value={formatBRL(stats.pagos)} accent="success" loading={loading} />
        </div>

        {/* GRID upload + chart */}
        <div className="grid gap-6 lg:grid-cols-5">
          <Card className="lg:col-span-2 border-border/60">
            <CardHeader>
              <CardTitle className="text-base">Processar novo boleto (IA)</CardTitle>
              <CardDescription>Extrai Linha Digitável e Valor via Visão Computacional</CardDescription>
            </CardHeader>
            <CardContent>
              <label
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  void handleFiles(e.dataTransfer.files);
                }}
                className={`group flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
                  dragOver ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-accent/30"
                } ${uploading ? "pointer-events-none opacity-60" : ""}`}
              >
                <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary group-hover:bg-primary/15">
                  {uploading ? <Loader2 className="h-6 w-6 animate-spin" /> : <UploadCloud className="h-6 w-6" />}
                </div>
                <p className="text-sm font-medium">{uploading ? "Analisando OCR…" : "Arraste a imagem do boleto aqui"}</p>
                <p className="mt-1 text-xs text-muted-foreground">ou clique para selecionar — PNG, JPG, WEBP</p>
                <input
                  type="file"
                  accept="application/pdf,image/png,image/jpeg,image/webp"
                  multiple
                  className="hidden"
                  disabled={uploading}
                  onChange={(e) => void handleFiles(e.target.files)}
                />
              </label>
            </CardContent>
          </Card>

          <Card className="lg:col-span-3 border-border/60">
            <CardHeader>
              <CardTitle className="text-base">Gastos por categoria</CardTitle>
              <CardDescription>Distribuição calculada em tempo real</CardDescription>
            </CardHeader>
            <CardContent className="h-[260px]">
              {chartData.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  {loading ? "Carregando…" : "Sem dados para exibir."}
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="categoria" stroke="var(--muted-foreground)" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke="var(--muted-foreground)" fontSize={11} tickLine={false} axisLine={false} />
                    <Tooltip
                      cursor={{ fill: "color-mix(in oklab, var(--primary) 8%, transparent)" }}
                      contentStyle={{
                        background: "var(--popover)",
                        border: "1px solid var(--border)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={(v: number) => formatBRL(v)}
                    />
                    <Bar dataKey="total" fill="var(--primary)" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>

        {/* TABELA DE BOLETOS COM CAMPOS EDITÁVEIS */}
        <Card className="border-border/60">
          <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
            <div>
              <CardTitle className="text-base">Boletos Cadastrados</CardTitle>
              <CardDescription>Clique diretamente no Nome ou Categoria para renomear</CardDescription>
            </div>
            <div className="relative w-full max-w-xs">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar beneficiário ou linha…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-8"
              />
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {/* Desktop View */}
            <div className="hidden md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[30%]">Beneficiário / Categoria</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead className="text-right">Valor</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Linha digitável</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading && filtered.length === 0 ? (
                    Array.from({ length: 4 }).map((_, i) => (
                      <TableRow key={i}>
                        <TableCell><Skeleton className="h-4 w-40" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                        <TableCell><Skeleton className="ml-auto h-4 w-16" /></TableCell>
                        <TableCell><Skeleton className="h-5 w-20 rounded-full" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                        <TableCell></TableCell>
                      </TableRow>
                    ))
                  ) : filtered.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="py-12 text-center text-sm text-muted-foreground">
                        <X className="mx-auto mb-2 h-6 w-6 opacity-40" />
                        Nenhum boleto encontrado no banco.
                      </TableCell>
                    </TableRow>
                  ) : (
                    filtered.map((b) => (
                      <TableRow key={b.id} className="group">
                        
                        {/* CÉLULA EDITÁVEL: NOME E CATEGORIA */}
                        <TableCell>
                          <input
                            type="text"
                            className="w-full rounded bg-transparent px-1 py-0.5 font-medium hover:bg-accent/50 focus:bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                            defaultValue={b.beneficiario}
                            onBlur={(e) => handleSalvarEdicao(b.id, e.target.value, b.categoria)}
                            title="Clique para editar o nome"
                          />
                          <input
                            type="text"
                            className="w-full rounded bg-transparent px-1 py-0.5 text-xs text-muted-foreground hover:bg-accent/50 focus:bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                            defaultValue={b.categoria}
                            onBlur={(e) => handleSalvarEdicao(b.id, b.beneficiario, e.target.value)}
                            title="Clique para editar a categoria"
                          />
                        </TableCell>

                        <TableCell>{formatDate(b.vencimento)}</TableCell>
                        <TableCell className="text-right font-mono">{formatBRL(b.valor)}</TableCell>
                        <TableCell>{statusBadge(b.status)}</TableCell>
                        <TableCell className="max-w-[220px] truncate font-mono text-xs text-muted-foreground">
                          {b.linhaDigitavel}
                        </TableCell>
                        
                        {/* COLUNA DE AÇÕES COM O OLHO 👁️ */}
                        <TableCell className="text-right space-x-1">
                          {b.url_imagem && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-muted-foreground hover:text-primary"
                              onClick={() => window.open(b.url_imagem || "", "_blank")}
                              title="Ver arquivo original da digitalização"
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          )}

                          {b.status !== "Pago" && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-8 border-success/50 text-success hover:bg-success/10"
                              onClick={() => handlePagar(b.id, b.beneficiario)}
                            >
                              <Check className="mr-1 h-3.5 w-3.5" /> Pagar
                            </Button>
                          )}

                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 opacity-0 group-hover:opacity-100"
                            title="Copiar Linha Digitável"
                            onClick={() => {
                              navigator.clipboard.writeText(b.linhaDigitavel);
                              toast.success("Linha digitável copiada");
                            }}
                          >
                            <Copy className="h-3.5 w-3.5" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>

            {/* Mobile View */}
            <div className="space-y-3 p-4 md:hidden">
              {loading && filtered.length === 0 ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="rounded-lg border border-border/60 p-4">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="mt-2 h-3 w-1/2" />
                    <Skeleton className="mt-3 h-5 w-20 rounded-full" />
                  </div>
                ))
              ) : filtered.length === 0 ? (
                <div className="py-10 text-center text-sm text-muted-foreground">
                  <X className="mx-auto mb-2 h-6 w-6 opacity-40" />
                  Nenhum boleto encontrado no banco.
                </div>
              ) : (
                filtered.map((b) => (
                  <div key={b.id} className="rounded-lg border border-border/60 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1">
                        {/* INPUTS MOBILE */}
                        <input
                          type="text"
                          className="w-full rounded bg-transparent font-medium focus:bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                          defaultValue={b.beneficiario}
                          onBlur={(e) => handleSalvarEdicao(b.id, e.target.value, b.categoria)}
                        />
                        <input
                          type="text"
                          className="w-full rounded bg-transparent text-xs text-muted-foreground focus:bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                          defaultValue={b.categoria}
                          onBlur={(e) => handleSalvarEdicao(b.id, b.beneficiario, e.target.value)}
                        />
                      </div>
                      {statusBadge(b.status)}
                    </div>

                    <div className="mt-3 flex items-end justify-between">
                      <div>
                        <div className="text-xs text-muted-foreground">Vencimento</div>
                        <div className="text-sm">{formatDate(b.vencimento)}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-muted-foreground">Valor</div>
                        <div className="font-mono text-base font-semibold">{formatBRL(b.valor)}</div>
                      </div>
                    </div>
                    
                    {/* LINHA DIGITÁVEL E AÇÕES NO MOBILE */}
                    <div className="mt-3 flex flex-col gap-2">
                      <div className="flex items-center gap-2 rounded-md bg-muted px-2 py-1.5">
                        <code className="flex-1 truncate font-mono text-[10px] text-muted-foreground">{b.linhaDigitavel}</code>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 shrink-0"
                          onClick={() => {
                            navigator.clipboard.writeText(b.linhaDigitavel);
                            toast.success("Copiado");
                          }}
                        >
                          <Copy className="h-3 w-3" />
                        </Button>
                      </div>

                      <div className="flex gap-2 mt-1">
                        {b.url_imagem && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="flex-1"
                            onClick={() => window.open(b.url_imagem || "", "_blank")}
                          >
                            <Eye className="mr-2 h-4 w-4" /> Ver Imagem
                          </Button>
                        )}

                        {b.status !== "Pago" && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="flex-1 border-success/50 text-success hover:bg-success/10"
                            onClick={() => handlePagar(b.id, b.beneficiario)}
                          >
                            <Check className="mr-2 h-4 w-4" /> Pagar
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
  loading,
}: {
  icon: typeof Wallet;
  label: string;
  value: string;
  accent: "primary" | "violet" | "success";
  loading?: boolean;
}) {
  const cls =
    accent === "primary"
      ? "bg-primary/10 text-primary"
      : accent === "violet"
        ? "bg-violet/10 text-violet"
        : "bg-success/10 text-success";
  return (
    <Card className="border-border/60">
      <CardContent className="flex items-start justify-between p-5">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
          {loading ? (
            <Skeleton className="mt-2 h-7 w-28" />
          ) : (
            <div className="mt-2 text-2xl font-bold tracking-tight">{value}</div>
          )}
        </div>
        <div className={`inline-flex h-10 w-10 items-center justify-center rounded-lg ${cls}`}>
          <Icon className="h-5 w-5" />
        </div>
      </CardContent>
    </Card>
  );
}
