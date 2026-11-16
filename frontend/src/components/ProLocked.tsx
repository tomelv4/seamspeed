import { useRouter } from "expo-router";

import { EmptyState, PrimaryButton } from "@/src/components/ui";

export function ProLocked({ title, body, testID }: { title: string; body: string; testID: string }) {
  const router = useRouter();
  return (
    <EmptyState testID={testID} icon="lock-closed" title={title} body={body}>
      <PrimaryButton testID={`${testID}-unlock`} label="Unlock PaceSensei Pro" icon="flash" onPress={() => router.push("/paywall")} />
    </EmptyState>
  );
}
