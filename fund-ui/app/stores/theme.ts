'use client'
import { create } from 'zustand'

interface ThemeStore { dark: boolean; toggle: () => void }
export const useTheme = create<ThemeStore>((set) => ({
  dark: true,
  toggle: () => set(s => { const d = !s.dark; document.documentElement.className = d ? 'dark' : 'light'; return { dark: d } }),
}))
