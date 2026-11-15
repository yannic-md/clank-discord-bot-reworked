"""The screens of the "Buttons & Dropdowns" editor, described once for both builders.

The embed builder and the container builder show the very same screens - the overview of the clickable elements, their
actions, restrictions, options and forms - and every click on them does the same. What differs is only how a screen is
drawn: as an embed with a classic view, or as a container in a layout view. So a screen is described here as data (its
texts and rows of controls, see `spec`), including what each control does, and each builder turns that description into
its own kind of view.

* `spec` - the pieces a screen is made of, and what a builder has to provide.
* `controls` - the buttons and dropdowns the screens are built from.
* `common` - small helpers several screens share.
* `host` - the part of a builder that switches between screens.
* `hub`, `options`, `actions`, `action_editors`, `conditions`, `questions` - the screens themselves.
"""
