import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";
import { Logo } from "./Logo";

export function Header() {
  const { theme, toggle } = useTheme();

  return (
    <header className="sticky top-0 z-50 border-b border-border/50 glass">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 md:px-6">
        <Logo />
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={toggle} aria-label="Alternar tema">
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </header>
  );
}
