import { Button, Card, createTheme, type MantineColorsTuple } from '@mantine/core'

// The PJ Tricia deck: a black stage, the logo's marker red, the gold of the round titles, and
// the lightbulb's cream. Marker Felt is on every Apple device; elsewhere Permanent Marker stands in.
export const MARKER_FONT = "'Marker Felt', 'Permanent Marker', 'Comic Sans MS', cursive"

const marker: MantineColorsTuple = [
  '#fdeeec',
  '#f7d3ce',
  '#eeaca3',
  '#e48477',
  '#da6354',
  '#cf5444',
  '#c0483a',
  '#a33c30',
  '#863127',
  '#69261e',
]

const gold: MantineColorsTuple = [
  '#fff7e6',
  '#ffeac2',
  '#fbd88f',
  '#f5c25c',
  '#f0ae3c',
  '#e39d24',
  '#c78516',
  '#9f6a10',
  '#7a510b',
  '#553805',
]

const cream: MantineColorsTuple = [
  '#fefdf2',
  '#fcfadf',
  '#f8f4bc',
  '#f1ea98',
  '#e9df76',
  '#ddd05a',
  '#c4b744',
  '#9d9235',
  '#766e27',
  '#4f4919',
]

// Mantine's dark scheme draws the page from dark.7 and cards from dark.6.
const dark: MantineColorsTuple = [
  '#ececec',
  '#c6c6c6',
  '#9a9a9a',
  '#707070',
  '#3a3a3a',
  '#2a2a2a',
  '#151515',
  '#000000',
  '#000000',
  '#000000',
]

export const theme = createTheme({
  primaryColor: 'marker',
  primaryShade: 6,
  colors: { marker, gold, cream, dark },
  fontFamily: "'Helvetica Neue', Helvetica, Arial, system-ui, sans-serif",
  headings: { fontFamily: MARKER_FONT, fontWeight: '700' },
  defaultRadius: 'md',
  components: {
    Card: Card.extend({ defaultProps: { radius: 'lg', withBorder: true } }),
    Button: Button.extend({ defaultProps: { radius: 'xl' } }),
  },
})
