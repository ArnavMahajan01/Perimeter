import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** A render error anywhere would otherwise blank the whole native window,
 * which reads as "the app crashed". Show the error instead. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
          <div className="text-[15px] font-semibold">Something went wrong in the interface</div>
          <pre className="max-w-[560px] rounded-lg border bg-card p-4 text-left font-mono text-xs whitespace-pre-wrap text-destructive">
            {this.state.error.message}
          </pre>
          <button
            className="rounded-md bg-primary px-4 py-2 text-[13px] font-medium text-primary-foreground"
            onClick={() => this.setState({ error: null })}
          >
            Reload view
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
