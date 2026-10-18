import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as DropdownPrimitive from '@radix-ui/react-dropdown-menu'
import * as PopoverPrimitive from '@radix-ui/react-popover'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import clsx, { type ClassValue } from 'clsx'
import { Loader2, X } from 'lucide-react'
import {
  forwardRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'

import { twMerge } from 'tailwind-merge'

/** Join class names; later Tailwind classes override earlier conflicting ones. */
export function cx(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

// -- buttons ------------------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle'

const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'bg-accent-600 text-white hover:bg-accent-500 disabled:hover:bg-accent-600',
  secondary:
    'bg-surface-800 text-zinc-200 border border-surface-600 hover:bg-surface-700 hover:border-zinc-500',
  ghost: 'text-zinc-300 hover:bg-surface-800 hover:text-zinc-100',
  subtle: 'text-zinc-400 hover:text-zinc-100',
  danger: 'bg-red-600/90 text-white hover:bg-red-500',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: 'xs' | 'sm' | 'md'
  icon?: ReactNode
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', icon, loading, className, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled || loading}
      className={cx(
        'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-500',
        'disabled:cursor-not-allowed disabled:opacity-50',
        size === 'xs' && 'h-6 px-1.5 text-xs',
        size === 'sm' && 'h-7 px-2 text-xs',
        size === 'md' && 'h-8 px-3 text-sm',
        !children && (size === 'xs' ? 'w-6 px-0' : size === 'sm' ? 'w-7 px-0' : 'w-8 px-0'),
        buttonVariants[variant],
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" /> : icon}
      {children}
    </button>
  )
})

// -- form fields ------------------------------------------------------------------------

const fieldBase =
  'w-full rounded-md border border-surface-700 bg-surface-900 text-sm text-zinc-100 placeholder:text-zinc-600 ' +
  'focus:border-accent-600 focus:ring-1 focus:ring-accent-600 focus:outline-none disabled:opacity-50'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cx(fieldBase, 'h-8 px-2.5', className)} {...props} />
  },
)

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cx(fieldBase, 'px-2.5 py-1.5', className)} {...props} />
  },
)

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...props }, ref) {
    return (
      <select ref={ref} className={cx(fieldBase, 'h-8 px-2 pr-7', className)} {...props}>
        {children}
      </select>
    )
  },
)

export function Checkbox({
  checked,
  onChange,
  label,
  className,
  title,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: ReactNode
  className?: string
  title?: string
}) {
  return (
    <label
      className={cx('inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-300', className)}
      title={title}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 rounded border-surface-600 bg-surface-900 accent-cyan-500"
      />
      {label}
    </label>
  )
}

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label?: ReactNode
  hint?: ReactNode
  error?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cx('flex flex-col gap-1', className)}>
      {label && <div className="text-xs font-medium text-zinc-400">{label}</div>}
      {children}
      {error ? (
        <div className="text-xs text-red-400">{error}</div>
      ) : hint ? (
        <div className="text-xs text-zinc-500">{hint}</div>
      ) : null}
    </div>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  size = 'sm',
}: {
  value: T
  options: { value: T; label: ReactNode; title?: string }[]
  onChange: (value: T) => void
  size?: 'xs' | 'sm'
}) {
  return (
    <div className="inline-flex rounded-md border border-surface-700 bg-surface-900 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cx(
            'rounded px-2 font-medium transition-colors',
            size === 'xs' ? 'h-5 text-[11px]' : 'h-6 text-xs',
            value === o.value
              ? 'bg-surface-700 text-zinc-100'
              : 'text-zinc-500 hover:text-zinc-200',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// -- small display bits ---------------------------------------------------------------------

export function Badge({
  children,
  tone = 'neutral',
  className,
  title,
}: {
  children: ReactNode
  tone?: 'neutral' | 'error' | 'warning' | 'success' | 'accent'
  className?: string
  title?: string
}) {
  const tones = {
    neutral: 'bg-surface-700 text-zinc-300',
    error: 'bg-red-500/15 text-red-300',
    warning: 'bg-amber-500/15 text-amber-300',
    success: 'bg-emerald-500/15 text-emerald-300',
    accent: 'bg-accent-500/15 text-accent-300',
  }
  return (
    <span
      title={title}
      className={cx(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] leading-none font-medium',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-surface-600 bg-surface-800 px-1 font-mono text-[10px] text-zinc-400">
      {children}
    </kbd>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx('size-4 animate-spin text-zinc-500', className)} />
}

export function Empty({
  icon,
  title,
  children,
}: {
  icon?: ReactNode
  title: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      {icon && <div className="text-zinc-600">{icon}</div>}
      <div className="text-sm font-medium text-zinc-300">{title}</div>
      {children && <div className="max-w-sm text-sm text-zinc-500">{children}</div>}
    </div>
  )
}

export function SectionTitle({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <h3 className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">{children}</h3>
      {actions}
    </div>
  )
}

// -- overlays -------------------------------------------------------------------------------

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          className={cx(
            'fixed top-[12vh] left-1/2 z-50 flex max-h-[76vh] w-[calc(100vw-2rem)] -translate-x-1/2 flex-col',
            'rounded-lg border border-surface-600 bg-surface-850 shadow-2xl focus:outline-none',
            wide ? 'max-w-4xl' : 'max-w-lg',
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-surface-700 px-5 py-3.5">
            <div>
              <DialogPrimitive.Title className="text-base font-semibold text-zinc-100">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-0.5 text-sm text-zinc-400">
                  {description}
                </DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close asChild>
              <Button variant="ghost" size="sm" icon={<X className="size-4" />} aria-label="Close" />
            </DialogPrimitive.Close>
          </div>
          {children && <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>}
          {footer && (
            <div className="flex justify-end gap-2 border-t border-surface-700 px-5 py-3">
              {footer}
            </div>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export const Menu = DropdownPrimitive.Root
export const MenuTrigger = DropdownPrimitive.Trigger

export function MenuContent({ children, align = 'end' }: { children: ReactNode; align?: 'start' | 'end' }) {
  return (
    <DropdownPrimitive.Portal>
      <DropdownPrimitive.Content
        align={align}
        sideOffset={4}
        className="z-50 min-w-44 rounded-md border border-surface-600 bg-surface-800 p-1 shadow-xl"
      >
        {children}
      </DropdownPrimitive.Content>
    </DropdownPrimitive.Portal>
  )
}

export function MenuItem({
  children,
  onSelect,
  icon,
  danger,
  disabled,
}: {
  children: ReactNode
  onSelect: () => void
  icon?: ReactNode
  danger?: boolean
  disabled?: boolean
}) {
  return (
    <DropdownPrimitive.Item
      disabled={disabled}
      onSelect={onSelect}
      className={cx(
        'flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm outline-none select-none',
        'data-[disabled]:cursor-not-allowed data-[disabled]:opacity-40',
        danger
          ? 'text-red-300 data-[highlighted]:bg-red-500/20'
          : 'text-zinc-200 data-[highlighted]:bg-surface-700',
      )}
    >
      {icon && <span className="text-zinc-400">{icon}</span>}
      {children}
    </DropdownPrimitive.Item>
  )
}

export function MenuSeparator() {
  return <DropdownPrimitive.Separator className="my-1 h-px bg-surface-600" />
}

export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger
export const PopoverAnchor = PopoverPrimitive.Anchor

export function PopoverContent({
  children,
  className,
  align = 'start',
}: {
  children: ReactNode
  className?: string
  align?: 'start' | 'center' | 'end'
}) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={4}
        onOpenAutoFocus={(e) => e.preventDefault()}
        className={cx(
          'z-50 rounded-md border border-surface-600 bg-surface-800 shadow-xl focus:outline-none',
          className,
        )}
      >
        {children}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  )
}

export function Tip({ content, children }: { content: ReactNode; children: ReactNode }) {
  if (!content) return <>{children}</>
  return (
    <TooltipPrimitive.Root delayDuration={350}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={4}
          className="z-50 max-w-xs rounded border border-surface-600 bg-surface-800 px-2 py-1 text-xs text-zinc-200 shadow-lg"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}

export const TooltipProvider = TooltipPrimitive.Provider
