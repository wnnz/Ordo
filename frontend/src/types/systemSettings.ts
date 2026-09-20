export type SystemSettingValue = number | boolean

export type SystemSetting = {
  key: string
  value: SystemSettingValue
  default: SystemSettingValue
  minimum: number | null
  maximum: number | null
  unit: string
  type: 'integer' | 'boolean'
  source: 'database' | 'environment'
}
