import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-sm text-center">
            <div className="text-3xl mb-3">⚠️</div>
            <h2 className="text-lg font-semibold text-gray-200 mb-2">
              页面出错了
            </h2>
            <p className="text-sm text-gray-400 mb-2">
              {this.state.error?.message || "发生了未知错误"}
            </p>
            <p className="text-xs text-gray-600 mb-4">
              请尝试刷新页面或返回首页
            </p>
            <div className="flex gap-2 justify-center">
              <button
                onClick={this.handleRetry}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm transition-colors"
              >
                重试
              </button>
              <button
                onClick={() => (window.location.href = "/")}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors"
              >
                返回首页
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
