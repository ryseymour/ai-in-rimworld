using HarmonyLib;
using RimWorld;
using Verse;
using Verse.AI;

namespace AiRim
{
    [StaticConstructorOnStartup]
    public static class Startup
    {
        static Startup()
        {
            new Harmony("ryseymour.airim").PatchAll();
            Transport.Start();
            Log.Message("[AiRim] patches applied");
        }
    }

    [HarmonyPatch(typeof(Pawn_JobTracker), nameof(Pawn_JobTracker.StartJob))]
    static class Patch_StartJob
    {
        static void Postfix(Pawn_JobTracker __instance, Pawn ___pawn, Job newJob)
        {
            if (__instance.curJob == newJob) Events.JobStart(___pawn, newJob);
        }
    }

    [HarmonyPatch(typeof(Pawn_JobTracker), nameof(Pawn_JobTracker.EndCurrentJob))]
    static class Patch_EndCurrentJob
    {
        static void Prefix(Pawn_JobTracker __instance, Pawn ___pawn, JobCondition condition, out Job __state)
        {
            __state = __instance.curJob;
        }

        static void Postfix(Pawn ___pawn, JobCondition condition, Job __state)
        {
            Events.JobEnd(___pawn, __state, condition);
        }
    }

    [HarmonyPatch(typeof(PlayLog), nameof(PlayLog.Add))]
    static class Patch_PlayLogAdd
    {
        static void Postfix(LogEntry entry)
        {
            if (entry is PlayLogEntry_Interaction inter)
            {
                var tr = Traverse.Create(inter);
                var initiator = tr.Field("initiator").GetValue<Pawn>();
                var recipient = tr.Field("recipient").GetValue<Pawn>();
                var def = tr.Field("intDef").GetValue<InteractionDef>();
                Events.Interaction(inter, initiator, recipient, def);
            }
        }
    }

    [HarmonyPatch(typeof(MentalStateHandler), nameof(MentalStateHandler.TryStartMentalState))]
    static class Patch_MentalState
    {
        static void Postfix(Pawn ___pawn, MentalStateDef stateDef, string reason, bool __result)
        {
            if (__result) Events.MentalState(___pawn, stateDef, reason);
        }
    }

    [HarmonyPatch(typeof(Pawn_HealthTracker), nameof(Pawn_HealthTracker.AddHediff), typeof(Hediff), typeof(BodyPartRecord), typeof(DamageInfo?), typeof(DamageWorker.DamageResult))]
    static class Patch_AddHediff
    {
        static void Postfix(Pawn ___pawn, Hediff hediff) => Events.Hediff(___pawn, hediff);
    }

    [HarmonyPatch(typeof(Pawn), nameof(Pawn.Kill))]
    static class Patch_Kill
    {
        static void Postfix(Pawn __instance, DamageInfo? dinfo) => Events.Death(__instance, dinfo);
    }

    [HarmonyPatch(typeof(LetterStack), nameof(LetterStack.ReceiveLetter), typeof(Letter), typeof(string), typeof(int), typeof(bool))]
    static class Patch_ReceiveLetter
    {
        static void Postfix(Letter let) => Events.Letter(let);
    }

    [HarmonyPatch(typeof(IncidentWorker), nameof(IncidentWorker.TryExecute))]
    static class Patch_Incident
    {
        static void Postfix(IncidentWorker __instance, IncidentParms parms, bool __result)
            => Events.Incident(__instance.def, parms, __result);
    }
}
