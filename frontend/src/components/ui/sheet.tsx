import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
export const Sheet = Dialog.Root
export const SheetTrigger = Dialog.Trigger
export const SheetClose = Dialog.Close
export const SheetTitle = Dialog.Title
export const SheetDescription = Dialog.Description
export const SheetContent = React.forwardRef<React.ComponentRef<typeof Dialog.Content>, React.ComponentPropsWithoutRef<typeof Dialog.Content>>(({ children, ...props }, ref) => <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/25 backdrop-blur-[2px]"/><Dialog.Content ref={ref} className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-slate-200 bg-white p-6 shadow-2xl outline-none" {...props}>{children}<Dialog.Close className="absolute right-5 top-5 rounded-md p-2 text-slate-500 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-blue-500" aria-label="关闭设置"><X size={18}/></Dialog.Close></Dialog.Content></Dialog.Portal>)
SheetContent.displayName = 'SheetContent'
