c234567
      program pvm5
c
c=====================================================================
c
c Adapted from pvm4.f
c Code written by David Lapola & Marcos Oyama
c Last updates
c MDO: 24 Aug 2007.
c DML: 27 Aug 2007.
c
c=====================================================================
c
c i/o variables
c d2wm : month of the transition between wet and dry season
c
      parameter(nx=192,ny=96)
      real*4 tmin(nx,ny),npp(nx,ny),snpp(nx,ny),hresp(nx,ny),
     &       csoil(nx,ny),photo(nx,ny),aresp(nx,ny), seai(nx,ny), 
     &       weti(nx,ny), ratioNPP(nx,ny)
      real*4 lsmk(nx,ny),bpot(nx,ny)
      real*4 wsoil2(nx,ny,12),waux2(12)
      real*4 ipar(nx,ny,12),avgpar(nx,ny)
      real ratio
      real*4 d2wm(nx,ny)
      real*4 u(nx,ny,12),anu(nx,ny,12),uwind(nx,ny,12),ud2w(nx,ny)
c
c set fire on/off
      mfire = 1 !0=off ; 1=on
c
c read environmental variables
      open(13,file='../outputs/ambientais4_100.bin',
     &        status='old',form='unformatted',
     &        access='direct',recl=nx*ny)
      read(13,rec=1) tmin   !oC
      read(13,rec=2) npp    !kgC/m2/y
      read(13,rec=3) snpp   !dimensionless
      read(13,rec=4) hresp  !kgC/m2/y
      read(13,rec=5) csoil  !kgC/m2/y
      read(13,rec=6) photo  !kgC/m2/y
      read(13,rec=7) aresp  !kgC/m2/y
      read(13,rec=8) seai   !dimensionless
      read(13,rec=9) weti   !dimensionless
      close(13)

***** MDO BEGIN
*     Read IPAR file and calculate annual average IPAR (avgpar).
      open(15,file='../inputs/ipar.bin',
     &        status='old',form='unformatted',
     &        access='direct',recl=nx*ny)
      call read12(15,ipar)
      close(15)

      do i=1,nx
      do j=1,ny
         avgpar(i,j) = 0.0
         do k=1,12
            avgpar(i,j) = avgpar(i,j) + ipar(i,j,k)/12.0
         enddo
      enddo
      enddo
***** MDO END
c
c read soil moisture (W, degree of saturation)
      open(14,file='../outputs/soilm_100.bin',
     &        status='old',form='unformatted',
     &        access='direct',recl=nx*ny)
      call read12(14,wsoil2)
      close(14)
c
c read uwind (850 hPa)
      open(15,file='../inputs/unew_100.bin',
     &        status='old',form='unformatted',
     &        access='direct',recl=nx*ny)
      call read12(15,u)
      close(15)
c
c read uwind anomalies (see line 71)
c      open(18,file='/home/david/ipcc_ar4/anomalias/SRESA2/uwind/'//
c     &               'HADCM3_A2_2070_2099_anom_u850.bin',status='old',
c     &        form='unformatted',access='direct',recl=nx*ny)
c      call read12(18,anu)
c      close(18)
c
c read lsmk
      open(16,file='../inputs/lsmk.bin',status='old',
     &        form='unformatted',access='direct',recl=nx*ny)
      read(16,rec=1) lsmk
c
c dry to wet season transition
      do i=1,nx
      do j=1,ny
         d2wm(i,j) = -999.99
         ud2w(i,j) = -999.99
ccc	 npp(i,j) = meanpp(i,j)*0.58	!test for reduction of NPP (Lapola's dissertation)
         if (wsoil2(i,j,1).ge.0.0) then
            do k=1,12
               waux2(k) = wsoil2(i,j,k)
	       uwind(i,j,k) = u(i,j,k)!+anu(i,j,k)
            enddo
            call findm (waux2, moaux2) !find month
            d2wm(i,j) = real(moaux2)
            mr = moaux2 + 1 !month right after d2w transition month
ccc            mr = moaux2 !d2w month
            if (mr.eq.13) mr = 1
            ud2w(i,j) = uwind(i,j,mr) !dry to wet U-wind
         endif
      enddo
      enddo
c
c for all grid points
      do i=1,nx
      do j=1,ny
      nbio = int(lsmk(i,j))
c
c ocean grid points
      if (nbio.eq.0) then
      bpot(i,j) = 0.
      ratioNPP(i,j) = 0. 
      goto 1000
      endif
c
c land grid points
      bpot(i,j) = -1.
      ratioNPP(i,j) = ratio(npp(i,j),avgpar(i,j))

***** MDO BEGIN
* Rules for biome allocation.

c desert and semi-desert
      if (tmin(i,j).ge.-15.0) then
         if (tmin(i,j).le.10.0) then !extratropical region
            if (ratio(npp(i,j),avgpar(i,j)).le.0.05) then
               bpot(i,j) = 11.0 !desert
            else
               if (ratio(npp(i,j),avgpar(i,j)).le.0.28) bpot(i,j) = 9.0 !semi-desert
            endif
         else !tropical region
            if (ratio(npp(i,j),avgpar(i,j)).le.0.005) then
               bpot(i,j) = 11.0 !desert
            else
               if (ratio(npp(i,j),avgpar(i,j)).le.0.15) bpot(i,j) = 9.0 !semi-desert
            endif
         endif
      endif

      if (bpot(i,j).eq.-1.0) then !remaining land grid points...

c ice, tundra, larch
      if (tmin(i,j).le.-27.0) then
         if (ratio(npp(i,j),avgpar(i,j)).eq.0.0) then
            bpot(i,j) = 20.0 !ice
         else
            if (ratio(npp(i,j),avgpar(i,j)).le.0.3) then
               bpot(i,j) = 10.0 !tundra
            else
               bpot(i,j) = 5.0 !larch
            endif
         endif
      endif

c remaining tundra, boreal forest, grasslands
      if (tmin(i,j).gt.-27.0 .and. tmin(i,j).le.-9.0) then
         if (ratio(npp(i,j),avgpar(i,j)).le.0.08) then
            bpot(i,j) = 10.0 !remaining tundra
         else
            if (avgpar(i,j).le.58.0) then
               bpot(i,j) = 4.0 !boreal forest
            else
               bpot(i,j) = 7.0 !grasslands
            endif
         endif
      endif

c mixed forest, grasslands
      if (tmin(i,j).gt.-9.0 .and. tmin(i,j).le.-6.0) then
         if (ratio(npp(i,j),avgpar(i,j)).le.0.5) then
c         if (ratio(npp(i,j),avgpar(i,j)).le.0.6) then
            bpot(i,j) = 7.0 !grasslands
         else
            bpot(i,j) = 3.0 !mixed forest
         endif
      endif

c temperate forest, grasslands
      if (tmin(i,j).gt.-6.0 .and. tmin(i,j).le.10.0) then
         if (ratio(npp(i,j),avgpar(i,j)).le.0.7) then
            bpot(i,j) = 7.0 !grasslands
         else
            bpot(i,j) = 2.0 !temperate forest
         endif
      endif

c tropical biomes
      if (tmin(i,j).gt.10.0) then
         if (snpp(i,j).gt.0.1) then
            if (ratio(npp(i,j),avgpar(i,j)).le.0.38) then
               bpot(i,j) = 8.0 !caatinga
            else
               bpot(i,j) = 6.0 !savanna
            endif
         else
            if (ratio(npp(i,j),avgpar(i,j)).le.0.72) then
                bpot(i,j) = 13.0 !seasonal forest
            else
                bpot(i,j) = 1.0 !ombrophyllous forest
            endif
         endif
      endif

      endif
*
***** MDO END
*
      if (mfire.eq.1) then !fire parameterization is on
***** Natural fire parameterization from U-wind (to correct India)
      ulim = 1.5 !obtained after the best results with observed lightning
         if (int(bpot(i,j)).eq.6.) then
            if (ud2w(i,j).le.ulim) then !fire!!!
            bpot(i,j) = 6.0
	    else !no fire!!!
            bpot(i,j) = 13.0
	    endif
         endif
      else !fire parameterization is off
      continue
      endif
c
      if (bpot(i,j).eq.-1.0) then
         print *, 'Error: no biome grid cell!'
         stop
      endif
c
 1000 continue
c
      enddo
      enddo
c
      if (mfire.eq.0) then
      open(17,file='../outputs/bpot4off_100.bin',
     &        status='unknown',form='unformatted',
     &        access='direct',recl=nx*ny)
      else
      open(17,file='../outputs/bpot4on_100.bin',
c      open(17,file='../ipcc_env_vars2/bpot4on_'//
c     &    'HADCM3_A2_co2onlyRc.bin',
     &        status='unknown',form='unformatted',
     &        access='direct',recl=nx*ny)
      endif
      write(17,rec=1) bpot
      write(17,rec=2) npp
      write(17,rec=3) snpp
      write(17,rec=4) ratioNPP
      write(17,rec=5) hresp
      write(17,rec=6) csoil
      write(17,rec=7) d2wm
      write(17,rec=8) ud2w
      write(17,rec=9) photo
      write(17,rec=10) aresp
      write(17,rec=11) seai
      write(17,rec=12) weti
c
      close(17)
c
      stop
      end
c
c=======================================================================
c
***** MDO BEGIN
* Ratio between NPP and maximum reference NPP (from IPAR).
      real function ratio (anpp, apar)
      real anpp, apar
      real refval
      refval = amax1((apar - 35.0)/45.0,0.0)
      if (refval .eq. 0.0) then
         ratio = 0.0 !independente de PAR
      else
         ratio = anpp/refval
         ratio = amax1(ratio,0.0)
         ratio = amin1(ratio,1.0)
      endif
      return
      end
***** MDO END
c
c=======================================================================
c
      subroutine read12 (nunit,var)
c auxiliar reading routine
      parameter(nx=192,ny=96)
      integer nunit
      real*4 var(nx,ny,12)
      real*4 aux(nx,ny)
      do k=1,12
        read(nunit,rec=k) aux
        do i=1,nx
          do j=1,ny
            var(i,j,k) = aux(i,j)
          enddo
        enddo
      enddo
      return
      end

c=======================================================================

      subroutine findm (w, m)

      real*4 w(12), w2(12), w3(12), dw(12)
      integer m, m3(12)

      wmax = -10.0
      wmin =  10.0
      do k=1,12
         w2(k) = w(k)
         if (w(k).gt.wmax) wmax=w(k)
         if (w(k).lt.wmin) wmin=w(k)
      enddo
c em media, deveria ser dividido por 6; a ideia eh que a restricao
c nao seja tao grande
      wlim = (wmax-wmin)/8.0
c      print *, wlim

      do iter=1,12
         wmin = 10.0
         do k=1,12
            if (w2(k).lt.wmin) then
               wmin = w2(k)
               mmin = k
            endif
         enddo
         w3(iter) = wmin
         m3(iter) = mmin
         if (mmin.ne.12) then
            dw(iter) = w(mmin+1)-w(mmin)
         else
            dw(iter) = w(1) - w(12)
         endif
         w2(mmin) = 100.0
      enddo
 
      iter=0
   10 continue
      iter=iter+1
      if (dw(iter).ge.wlim) then
      m = m3(iter)
      goto 99
      endif
      goto 10
   99 continue
 
      return
      end

c=======================================================================

