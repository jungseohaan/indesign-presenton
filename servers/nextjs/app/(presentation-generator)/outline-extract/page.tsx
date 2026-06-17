import React, { Suspense } from "react";
import { Metadata } from "next";
import Header from "@/app/(presentation-generator)/(dashboard)/dashboard/components/Header";
import OutlineExtractPage from "./components/OutlineExtractPage";

export const metadata: Metadata = {
  title: "Extract Outline",
  description:
    "Extract and refine a presentation outline from an uploaded InDesign document through chat.",
};

const page = () => {
  return (
    <div className="relative min-h-screen">
      <Header />
      <Suspense fallback={null}>
        <OutlineExtractPage />
      </Suspense>
    </div>
  );
};

export default page;
