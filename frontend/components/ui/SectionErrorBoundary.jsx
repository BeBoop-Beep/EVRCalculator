"use client";

import { Component } from "react";
import SectionErrorPanel from "@/components/ui/SectionErrorPanel";

// This codebase has no React error boundaries anywhere else today. This one
// exists so a render-time exception in one section (e.g. a chart choking on
// malformed data, even though its fetch succeeded) shows the same localized
// SectionErrorPanel as a fetch failure, instead of taking down the whole tab
// (or the whole page, which is the default behavior with no boundary at all).
//
// resetKeys lets a caller clear a previously-caught error without a full
// reload — e.g. pass [resolvedSetResourceId] so switching sets resets it.
export default class SectionErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    if (process.env.NODE_ENV !== "production") {
      console.error(`[section-error-boundary] ${this.props.sectionName || "section"}`, error, errorInfo);
    }
  }

  componentDidUpdate(prevProps) {
    if (!this.state.hasError) {
      return;
    }
    const prevKeys = prevProps.resetKeys || [];
    const nextKeys = this.props.resetKeys || [];
    const changed =
      prevKeys.length !== nextKeys.length || prevKeys.some((key, index) => key !== nextKeys[index]);
    if (changed) {
      this.setState({ hasError: false, error: null });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <SectionErrorPanel
          title={this.props.title}
          message={this.props.errorMessage || "This section hit an unexpected error."}
          onRetry={
            this.props.onRetry ||
            (() => this.setState({ hasError: false, error: null }))
          }
          minHeightClassName={this.props.minHeightClassName}
          className={this.props.className}
        />
      );
    }
    return this.props.children;
  }
}
