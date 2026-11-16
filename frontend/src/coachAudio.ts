import { AudioPlayer, createAudioPlayer, setAudioModeAsync } from "expo-audio";

// One module-level player so only one coach voice ever plays at a time.
let player: AudioPlayer | null = null;

export async function playCoach(url: string) {
  await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
  if (!player) player = createAudioPlayer(url);
  else player.replace(url);
  player.play();
}

export function stopCoach() {
  try {
    player?.pause();
  } catch {}
}
