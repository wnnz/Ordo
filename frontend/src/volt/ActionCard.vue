<script setup lang="ts">
withDefaults(defineProps<{
  active?: boolean
  disabled?: boolean
  hoverable?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), { hoverable: true, type: 'button' })
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    class="surface focus-ring block rounded-xl text-left transition-[border-color] duration-150 disabled:pointer-events-none disabled:opacity-50"
    :class="[hoverable && 'card-hover', active && '!border-[var(--primary)] !bg-[var(--primary-soft)] !text-[var(--primary)]']"
  ><slot /></button>
</template>
