#!/usr/bin/env bash
# ~/.claude/statusline-command.sh
# Statusline derived from ~/.bashrc PS1:
#   \[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$
# Trailing "$" removed per statusLine conventions.

input=$(cat)
echo "$input" > /home/kcreasey/Documents/claude_stdin.json
cwd=$(echo "$input" | jq -r '.cwd // .workspace.current_dir // ""')
user=$(whoami)
host=$(hostname -s)

#Colors & Font effects
RESET=$'\033[00m'
## Colors
RED=$'\033[31m';
GREEN=$'\033[32m';
YELLOW=$'\033[33m';
BLUE=$'\033[34m';
MAGENTA=$'\033[35m';
CYAN=$'\033[36m';
WHITE=$'\033[37m';
perc_color () {
	VALUE=$(echo
	if [ $1 -ge 90 ]; then COLOR="$RED"
	elif [ $1 -ge 70 ]; then COLOR="$YELLOW"
	else COLOR="$GREEN"
	fi
	echo $COLOR
}
# $1 Sunrise; $2 Sunset
function sunriseset() {
	SUNBLOCK=""
	NOW=$(date +%H%M%S)
	SUNRISE=${1//:}
	SUNSET=${2//:}
	if [ "$NOW" -lt "$SUNRISE" ]; then SUNBLOCK="🌅$(date --date=$1 '+%I:%M%P')"
	elif [ "$NOW" -lt "$SUNSET" ]; then SUNBLOCK="🌇$(date --date=$2 '+%I:%M%P')"
	else SUNBLOCK="🌃 (TEST) SUNRISE = ${1%:*}"
	fi
	echo $SUNBLOCK
}
#####
input=$(cat)
echo "$input" > /home/kcreasey/Documents/claude_stdin.json
#####
cwd=$(echo "$input" | jq -r '.cwd // .workspace.current_dir // ""')
user=$(whoami)
host=$(hostname -s)

used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
model=$(echo "$input" | jq -r '.model.display_name // empty')

#Rate Limits
five_hour=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // 0' | cut -d. -f1)
five_hour_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // 0')
weekly=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // 0' | cut -d. -f1)
weekly_reset=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // 0')
RATE_BAR="$(printf "⏳%s|🗓️%s" "$(perc_color $five_hour)${five_hour}%${RESET}" "  $(perc_color $weekly)${weekly}%${RESET}")"

#Weather
IFS='|' read -r CC TEMP PRECIP SUNRISE SUNSET < <(curl -s "wttr.in/?format=%c|%t|%p|%S|%s")
#CC=$(curl -s "wttr.in/?format=%c") && WX="${WX}${CC}"
#TEMP=$(curl -s "wttr.in/?format=%t") && WX="${WX}${TEMP#+}"
WX="${CC} ${TEMP#+}"
[ "$PRECIP" != "0.0in" ] && WX="${WX}|🌧️${precip}"
WX="${WX}|$(sunriseset $SUNRISE $SUNSET)"


# Progress bar
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
BAR_WIDTH=20
FILLED=$((PCT * BAR_WIDTH / 100))
EMPTY=$((BAR_WIDTH - FILLED))
BAR=""
[ "$FILLED" -gt 0 ] && printf -v FILL "%${FILLED}s" && BAR="${FILL// /▓}"
[ "$EMPTY" -gt 0 ] && printf -v PAD "%${EMPTY}s" && BAR="${BAR}${PAD// /░}"
BAR_COLOR="$(perc_color $PCT)"
#if [ "$PCT" -ge 90 ]; then BAR_COLOR="$RED"
#elif [ "$PCT" -ge 70 ]; then BAR_COLOR="$YELLOW"
#else BAR_COLOR="$GREEN"; fi

BAR_BLOCK=${BAR_COLOR}${BAR}${RESET}

# Bold green user@host, reset, colon, bold blue cwd, reset
ps1_part=$(printf '\033[01;32m%s@%s\033[00m:\033[01;34m%s\033[00m' "$user" "$host" "$cwd")


if [ -n "$used" ] && [ -n "$model" ]; then
    printf '%s [%s]\n' "$ps1_part" "$WX"
    printf '[%s] %s|%s%% [%s] \n' "$model" "$BAR_BLOCK"  "$(printf '%.0f' "$used")" "$RATE_BAR"
elif [ -n "$model" ]; then
    printf '%s  [%s] [%s]' "$ps1_part" "$model" "$WX"
    printf '[%s]' "$RATE_BAR"
else
    printf '%s [%s]\n' "$ps1_part" "$WX"
    printf '[%s]' "$RATE_BAR"
fi
