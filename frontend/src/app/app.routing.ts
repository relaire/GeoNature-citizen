import { AboutComponent } from "./about/about.component";
import { ModuleWithProviders } from "@angular/core";
import { Routes, RouterModule } from "@angular/router";

import { HomeComponent } from "./home/home.component";
import { ObsComponent } from "./programs/observations/obs.component";
import { SitesComponent } from "./programs/sites/sites.component";
import { PageNotFoundComponent } from "./page-not-found/page-not-found.component";
import { ProgramsComponent } from "./programs/programs.component";
import { ProgramsResolve } from "./programs/programs-resolve.service";
import { UniqueProgramGuard } from "./programs/default-program.guard";
import { UserDashboardComponent } from "./auth/user-dashboard/user-dashboard.component";
import { SpeciesComponent } from "./synthesis/species/species.component";
import { AuthGuard } from "./auth/auth.guard";
import { SiteFormComponent } from "./programs/sites/form/form.component";
import {SiteDetailComponent} from "./programs/sites/detail/detail.component";

const appRoutes: Routes = [
  {
    path: "",
    redirectTo: "home",
    pathMatch: "full"
  },
  {
    path: "home",
    component: HomeComponent,
    canActivate: [UniqueProgramGuard],
    resolve: { programs: ProgramsResolve }
  },
  { path: "about", component: AboutComponent },
  {
    path: "mydashboard",
    component: UserDashboardComponent,
    canActivate: [AuthGuard]
  },
  {
    path: "programs",
    component: ProgramsComponent,
    resolve: { programs: ProgramsResolve }
  },
  {
    path: "programs/:id/observations",
    component: ObsComponent,
    resolve: { programs: ProgramsResolve }
  },
  {
    path: "programs/:id/sites",
    // component: SiteFormComponent,
    component: SitesComponent,
    resolve: { programs: ProgramsResolve }
  },
  { path: "synthesis/species/:id", component: SpeciesComponent },
  { path: "sites/detail/:id", component: SiteDetailComponent },
  { path: "**", component: PageNotFoundComponent }
];

export const routing: ModuleWithProviders = RouterModule.forRoot(appRoutes, {
  useHash: false,
  // enableTracing: true,
  scrollPositionRestoration: "enabled",
  anchorScrolling: "enabled",
  scrollOffset: [0, 113] // TODO: source from conf: router-outlet height
});
