import { Button, Card, createTheme, type MantineColorsTuple } from '@mantine/core'

// Cozy night in: midnight indigo, lamp-light gold, and a coral for the misses.
const midnight: MantineColorsTuple = [
  '#eeedf8',
  '#d6d4ee',
  '#b0acdc',
  '#8882c9',
  '#6760b8',
  '#534cab',
  '#463f99',
  '#39337f',
  '#2a2660',
  '#1c1a3a',
]

const gold: MantineColorsTuple = [
  '#fff7e6',
  '#ffeac2',
  '#fdd88d',
  '#fac65a',
  '#f5b83d',
  '#e9a51f',
  '#c98a10',
  '#9f6c0b',
  '#7a5208',
  '#553905',
]

const dark: MantineColorsTuple = [
  '#ecebf7',
  '#c4c2dd',
  '#9b98bf',
  '#77749e',
  '#57547f',
  '#423f68',
  '#332f57',
  '#26234a',
  '#1c1a3a',
  '#141229',
]

export const theme = createTheme({
  primaryColor: 'midnight',
  primaryShade: { light: 6, dark: 3 },
  colors: { midnight, gold, dark },
  fontFamily: "'Nunito Variable', system-ui, -apple-system, 'Segoe UI', sans-serif",
  headings: {
    fontFamily: "'Fredoka Variable', 'Nunito Variable', system-ui, sans-serif",
    fontWeight: '600',
  },
  defaultRadius: 'md',
  components: {
    Card: Card.extend({ defaultProps: { radius: 'lg', withBorder: true } }),
    Button: Button.extend({ defaultProps: { radius: 'xl' } }),
  },
})
