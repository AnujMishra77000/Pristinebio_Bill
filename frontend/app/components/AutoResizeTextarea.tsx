"use client";

import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";

type AutoResizeTextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export function AutoResizeTextarea({ className = "", onInput, ...props }: AutoResizeTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function resize() {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }

  useLayoutEffect(() => {
    resize();
  }, [props.value]);

  return (
    <textarea
      {...props}
      ref={textareaRef}
      className={`min-h-[44px] resize-y overflow-hidden leading-6 ${className}`}
      onInput={(event) => {
        resize();
        onInput?.(event);
      }}
    />
  );
}
