"""Shared appearance and display formatting."""


STYLES = """
<style>
.block-container {max-width: 78rem; padding-top: 2.5rem; padding-bottom: 3rem;}
[data-testid="stSidebar"] {border-right: 1px solid #DCE6DE;}
[data-testid="stMetricValue"] {font-size: 1.75rem;}
.outfit-account-form {
  display: grid; gap: .55rem; padding: 1.2rem; border: 1px solid #CBD6D0; border-radius: .65rem;
}
.outfit-account-form input {
  width: 100%; min-height: 2.65rem; box-sizing: border-box; border: 1px solid #CBD6D0;
  border-radius: .55rem; padding: .55rem .7rem; color: #173D31; background: #E9EFEB;
}
.outfit-account-form small {color: #3B5B50; margin-bottom: .3rem;}
.outfit-password-field {position: relative;}
.outfit-password-field input {padding-right: 3rem;}
.outfit-password-toggle {
  position: absolute; top: 0; right: 0; height: 100%; padding: 0 .7rem;
  border: 0; background: transparent; color: #173D31; cursor: pointer;
}
.outfit-account-form [hidden] {display: none;}
.outfit-account-submit {
  min-height: 2.65rem; color: white; background: #173D31; border: 0;
  border-radius: .55rem; font-weight: 600; cursor: pointer;
}
.outfit-account-submit:disabled {opacity: .65; cursor: wait;}
.outfit-account-error {color: #A32A2A; margin: 0;}
.studio-intro {padding: 1.75rem 2rem; border-radius: 1.3rem; border: 1px solid #CBDBCE;
  background: #E6F0E8; margin-bottom: 1.2rem;}
.studio-intro small {color: #286450; letter-spacing: .15em; font-weight: 700;}
.studio-intro h1 {color: #173D31; margin: .35rem 0 .55rem; padding: 0;
  font-size: clamp(1.8rem, 4vw, 2.8rem); line-height: 1.2;}
.studio-intro p {color: #3B5B50; margin-bottom: 0;}
.color-swatch {display: inline-block; margin: .3rem .75rem .5rem 0;}
.color-chip {width: 5.3rem; height: 2.4rem; border: 1px solid #CBD6D0;
  border-radius: .55rem; display: block;}
.color-swatch small {color: #3B5B50; font-variant-numeric: tabular-nums;}
@media (max-width: 600px) {.studio-intro {padding: 1.3rem;}}
</style>
"""


def display_time(value):
    if not value:
        return ""
    return str(value).replace("T", " ")[:19]
