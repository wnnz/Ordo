<script setup lang="ts">
import { Plus } from 'lucide-vue-next'
withDefaults(defineProps<{ label: string; tone?: 'success' | 'warning' | 'orange' }>(), { tone: 'orange' })
</script>

<template>
  <button type="button" class="card-hover flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border bg-[var(--panel-subtle)] text-[11px] font-semibold" :class="tone === 'success' ? 'border-emerald-500 text-emerald-600' : tone === 'warning' ? 'border-amber-500 text-amber-600' : 'border-orange-500 text-orange-600'">{{ label }}<Plus :size="12" /></button>
</template>
