;RAW Viewer v0.0.1 by GNY
;
;gonullyourself.com
;

alias _init.debug {
  echo -s Starting in RAW view mode ..
  .debug -n @raw
}

alias rawview {
  if ($1 == on) {
    set %_config.debug on
    _init.debug
    echo $iif($window(@raw),@raw,-s) $timestamp RAW view now ON
    return
  }
  if ($1 == off) {
    unset %_config.debug
    .debug -c off
    echo $iif($window(@raw),@raw,-s) $timestamp RAW view now OFF
    return
  }
}

menu * {
  RawView
  .On:rawview on
  .Off:rawview off
}
on *:start: { $iif(%_config.debug,_init.debug) }
