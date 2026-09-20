// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { describe, expect, it } from 'vitest'
import { i18n } from '@/i18n'
import AvatarInitial from './AvatarInitial.vue'
import ChoiceCard from './ChoiceCard.vue'
import PanelSection from './PanelSection.vue'

const global = {
  plugins: [i18n, [PrimeVue, { unstyled: true }] as [typeof PrimeVue, { unstyled: boolean }]],
}

describe('shared component primitives', () => {
  it('renders initials consistently for named and unnamed users', () => {
    expect(mount(AvatarInitial, { props: { name: '王小明' }, global }).text()).toBe('王')
    expect(mount(AvatarInitial, { props: { name: '' }, global }).text()).toBe('?')
  })

  it('exposes selected state and preserves button interactions', async () => {
    const wrapper = mount(ChoiceCard, { props: { selected: true }, slots: { default: 'Workflow' }, global })
    expect(wrapper.classes()).toContain('border-[var(--primary)]')
    expect(wrapper.text()).toBe('Workflow')
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })

  it('composes a titled panel with icon, actions, and content slots', () => {
    const wrapper = mount(PanelSection, {
      props: { title: 'Settings', description: 'Configure defaults' },
      slots: { icon: '<span>icon</span>', actions: '<button>Save</button>', default: '<p>Body</p>' },
      global,
    })
    expect(wrapper.find('h2').text()).toBe('Settings')
    expect(wrapper.text()).toContain('Configure defaults')
    expect(wrapper.text()).toContain('icon')
    expect(wrapper.text()).toContain('Save')
    expect(wrapper.text()).toContain('Body')
  })
})
